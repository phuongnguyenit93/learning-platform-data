Câu 1. Dependency Injection (DI) thay đổi cách đối tượng nghiệp vụ nhận phụ thuộc như thế nào?
A. Đối tượng tự tạo mọi phụ thuộc bằng new ở từng method
B. Đối tượng lấy phụ thuộc từ một biến static dùng chung
C. Đối tượng tìm mọi dịch vụ qua singleton registry
D. Phụ thuộc được cung cấp từ bên ngoài lúc lắp ghép
Đáp án đúng: D

Câu 2. Điểm cốt lõi của Inversion of Control (IoC) trong việc lắp ghép ứng dụng là gì?
A. Quyền điều phối tạo và nối đối tượng chuyển ra ngoài
B. Từng service tự chọn container để giải quyết phụ thuộc
C. Mọi interface tự sinh implementation trong lúc chạy
D. Mỗi nghiệp vụ tạo một dependency graph riêng mỗi lần
Đáp án đúng: A

Câu 3. Vì sao constructor injection thường thích hợp cho phụ thuộc bắt buộc?
A. Cho phép tạo object chưa đủ deps rồi gán vào sau
B. Đặt rõ yêu cầu khi khởi tạo và dễ kiểm tra tính hợp lệ
C. Làm phụ thuộc được nạp lại ở mỗi lần gọi method
D. Buộc mọi implementation phải kế thừa một base class
Đáp án đúng: B

Câu 4. Một service không thể hoạt động nếu thiếu Repository; nên xử lý ra sao?
A. Kiểm tra Repository ngay khi khởi tạo service
B. Chỉ chờ đến khi gọi method rồi trả kết quả rỗng
C. Tạo Repository ngẫu nhiên khi reference bằng null
D. Đưa thiếu Repository thành cảnh báo log rồi chạy tiếp
Đáp án đúng: A

Câu 5. Composition root trong một ứng dụng Java có vai trò chính nào?
A. Chứa nghiệp vụ xử lý đơn hàng của tất cả các tầng
B. Định nghĩa toàn bộ SQL mà mỗi repository sử dụng
C. Tạo và nối các implementation vào object graph
D. Chỉ khai báo interface mà không tạo bất kỳ đối tượng nào
Đáp án đúng: C

Câu 6. Một OrderService tự gọi new HttpPaymentGateway() trong constructor; hệ quả gì về thiết kế?
A. Giảm ràng buộc vì service luôn tự kiểm soát việc tạo
B. Dễ test hơn vì gateway thật luôn được khởi tạo
C. Bảo đảm có thể đổi gateway mà không sửa service
D. Service bị gắn chặt với implementation cụ thể
Đáp án đúng: D

Câu 7. Muốn unit test OrderService nhưng không gửi HTTP thật, cách nào phù hợp?
A. Dùng gateway production rồi chặn kết nối ở router
B. Tiêm fake PaymentGateway có kết quả điều khiển được
C. Chuyển test thành kiểm tra nội dung file bytecode
D. Giữ new HttpPaymentGateway và kiểm tra log gửi tiền
Đáp án đúng: B

Câu 8. Khi một dependency có thể tùy chọn và thay sau khởi tạo, kỹ thuật nào có thể phù hợp?
A. Dùng constructor chỉ chứa mọi tham số tùy chọn
B. Tạo biến static cho mọi dependency còn thiếu
C. Setter injection với quy tắc trạng thái rõ ràng
D. Buộc container phải khởi tạo lại toàn bộ ứng dụng
Đáp án đúng: C

Câu 9. Một lớp dùng field injection ẩn các phụ thuộc mà không có constructor; nhược điểm thường gặp là gì?
A. Giảm hẳn khả năng thay implementation của interface
B. Khó thấy các phụ thuộc bắt buộc và khởi tạo thủ công
C. Làm mọi phụ thuộc được tự động immutable ở runtime
D. Không thể dùng annotation với field trong Java
Đáp án đúng: B

Câu 10. Một singleton service chứa biến lastRequestId có thể bị thay bởi nhiều request; vấn đề nào đáng chú ý?
A. Singleton luôn được runtime tạo lại cho mỗi request
B. Singleton tự cung cấp bộ nhớ riêng cho từng thread
C. DI container bảo đảm mọi field đều được khóa đồng bộ
D. State dùng chung có nguy cơ lẫn dữ liệu và race
Đáp án đúng: D

Câu 11. Vì sao dependency có scope theo request không nên bị lưu trực tiếp như state trong singleton lâu dài?
A. Vì có thể giữ sai dữ liệu sau khi request kết thúc
B. Vì mọi request bắt buộc phải chạy trên cùng thread
C. Vì singleton không được phép sử dụng bất kỳ interface
D. Vì scope request chỉ áp dụng cho các lớp có SQL
Đáp án đúng: A

Câu 12. Một service singleton cần truy cập thông tin request hiện tại; cơ chế nào thích hợp hơn lưu một instance request cố định?
A. Đổi request object thành global singleton mutable
B. Lưu request đầu tiên để dùng cho mọi người dùng
C. Tạo request object mới bằng reflection khi app khởi động
D. Dùng scoped provider/proxy lấy đúng instance hiện tại
Đáp án đúng: D

Câu 13. Hai service A và B phụ thuộc constructor lẫn nhau; dấu hiệu thiết kế nào nên xem xét?
A. Đây là yêu cầu mặc định khi dùng constructor injection
B. A và B luôn phải chia sẻ một cùng transaction database
C. Quan hệ phụ thuộc vòng có thể cần tách trách nhiệm
D. Mọi vòng tham chiếu đều được Java tự giải quyết
Đáp án đúng: C

Câu 14. DI có bắt buộc mọi class phải có interface riêng không?
A. Không; cần abstraction khi nó mang giá trị thiết kế
B. Có; container chỉ hỗ trợ class implements interface
C. Có; Java không cho constructor nhận concrete class
D. Không; vì DI chỉ dùng được với các static method
Đáp án đúng: A

Câu 15. Ứng dụng chọn bộ tính phí theo thị trường mỗi lần xử lý; cách tổ chức DI nào phù hợp?
A. Inject một implementation duy nhất và không được đổi
B. Inject factory/resolver tạo strategy theo thị trường
C. Cho service tự tạo mọi implementation qua new
D. Đặt mọi thuật toán vào một switch trong controller
Đáp án đúng: B

Câu 16. Nếu không dùng Spring hay một DI container, có thể thực hành DI bằng cách nào?
A. Bắt buộc viết class loader riêng thay Java runtime
B. Tạo static service locator rồi cho mọi lớp gọi tới
C. Dùng Java thuần truyền dependency qua constructor
D. Chuyển toàn bộ service sang method static không tham số
Đáp án đúng: C

Câu 17. Một dependency mở socket cần được đóng khi application dừng. Ai nên quản lý lifecycle?
A. Bất kỳ consumer nào gọi method cũng phải close ngay
B. Mỗi lần container trả bean phải mở socket mới
C. Bộ test luôn chịu trách nhiệm dọn cả môi trường production
D. Thành phần sở hữu lifecycle/scope của dependency
Đáp án đúng: D

Câu 18. Kiểm thử service có constructor injection giúp tách framework theo cách nào?
A. Bắt buộc bật full Spring context ở mọi unit test
B. Có thể tạo service trực tiếp bằng fake dependencies
C. Không cần assertion vì constructor xác minh nghiệp vụ
D. Không thể thay dependency khi lớp đã được khởi tạo
Đáp án đúng: B

Câu 19. Mẫu Service Locator thường kém minh bạch hơn constructor injection vì sao?
A. Các phụ thuộc được tìm ẩn trong thân phương thức
B. Bắt service khai báo rõ mọi phụ thuộc ở constructor
C. Loại bỏ hoàn toàn khả năng cấu hình dependency scope
D. Buộc phải sử dụng nhiều interface không có implementation
Đáp án đúng: A

Câu 20. Một service dùng thời gian hiện tại để kiểm tra hạn token; nên inject gì để test lặp lại ổn định?
A. Một static currentTimeMillis gọi trực tiếp từ service
B. Clock có thể cố định trong test và thay ở runtime
C. Một thread pool chạy timer theo đồng hồ của CI
D. Một constructor khác tạo ngẫu nhiên timestamp đầu vào
Đáp án đúng: B

Câu 21. Dependency rất tốn tài nguyên và chỉ dùng trong một nhánh hiếm; cách nào có thể trì hoãn khởi tạo?
A. Buộc tạo tại startup dù chưa có consumer nào cần
B. Tạo singleton chứa sẵn mọi phiên bản của dependency
C. Inject provider/factory rồi lấy instance khi cần
D. Tạo phụ thuộc bằng new bên trong mọi method dùng nó
Đáp án đúng: C

Câu 22. Phân biệt DI và Dependency Inversion Principle (DIP) thế nào?
A. DI chỉ dùng khi có DI container, DIP chỉ dùng cho Java
B. Cả hai đều yêu cầu mỗi đối tượng phải là singleton
C. DIP là cơ chế framework tự sinh class và interface
D. DI là cách cấp phụ thuộc; DIP nói về hướng phụ thuộc
Đáp án đúng: D

Câu 23. Container thấy hai implementation cùng một interface; cách lắp ghép nào giảm mơ hồ?
A. Dùng qualifier hoặc cấu hình chọn implementation
B. Để container tự chọn ngẫu nhiên theo thứ tự scan
C. Xóa contract interface rồi cast sang Object
D. Tạo lại cả hai implementation khi mỗi request tới
Đáp án đúng: A

Câu 24. Sau khi lắp object graph tại composition root, kiểm thử nào phát hiện wiring sai mà unit test có fake không thấy?
A. Chỉ chạy unit test của từng lớp mà không cấu hình DI
B. Kiểm tra code style của tất cả file constructor
C. Khởi động cấu hình thật và kiểm tra các bean/dependency
D. Chỉ so số method trên interface và implementation
Đáp án đúng: C
