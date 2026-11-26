Factory Method giải quyết vấn đề gì khi mã nghiệp vụ cần tạo đối tượng nhưng không nên biết lớp triển khai cụ thể?
Bạn giải thích vai trò của Product, Concrete Product, Creator và Concrete Creator trong Factory Method như thế nào?
Khi nào việc gọi trực tiếp new khiến mã phụ thuộc quá chặt vào một loại sản phẩm?
Bạn mô tả luồng một Creator gọi factory method rồi sử dụng sản phẩm qua interface ra sao?
Bạn thiết kế hợp đồng Product để các triển khai khác nhau đáp ứng cùng một hành vi như thế nào?
Bạn sẽ xác định hành vi nào thuộc Creator và hành vi nào thuộc Concrete Product dựa trên trách nhiệm nghiệp vụ ra sao?
Vì sao Creator có thể cung cấp một thuật toán chung trong khi lớp con quyết định loại sản phẩm được tạo?
Bạn phân biệt factory method có phần triển khai mặc định với factory method abstract ở những trường hợp nào?
Khi thêm một loại sản phẩm mới, bạn mở rộng hệ thống mà không sửa thuật toán chung của Creator như thế nào?
Bạn sẽ áp dụng nguyên tắc Open/Closed Principle khi thiết kế Creator và các lớp con ra sao?
Bạn phân biệt Factory Method theo GoF với một static factory method đơn giản trả về đối tượng bằng cách nào?
Khi một phương thức chứa switch theo loại sản phẩm, bạn lựa chọn Factory Method hay bảng đăng ký factory theo tiêu chí nào?
Bạn so sánh Factory Method với Abstract Factory khi cần tạo một sản phẩm so với một họ sản phẩm liên quan ra sao?
Trong tình huống nào Builder phù hợp hơn Factory Method dù cả hai đều liên quan đến khởi tạo đối tượng?
Bạn đánh giá chi phí phát sinh nhiều lớp Creator khi áp dụng Factory Method trong một hệ thống nhỏ như thế nào?
Bạn chọn lớp Creator là abstract class hay interface dựa trên khả năng chia sẻ thuật toán và trạng thái như thế nào?
Khi cần truyền cấu hình vào Concrete Product, bạn thiết kế tham số của factory method ra sao?
Bạn xử lý lỗi cấu hình không hỗ trợ một loại sản phẩm mà không trả về null âm thầm như thế nào?
Một factory method có thể trả về sản phẩm đã cache thay vì tạo đối tượng mới trong những điều kiện nào?
Bạn xác định vòng đời tài nguyên của sản phẩm do factory method tạo ra và bên chịu trách nhiệm đóng tài nguyên ra sao?
Nếu Product là một kết nối tới hệ thống ngoài, bạn phân biệt trách nhiệm tạo và quản lý connection pool như thế nào?
Bạn thiết kế Factory Method chọn bộ chuyển đổi định dạng dữ liệu theo loại đầu vào ra sao?
Khi hệ thống hỗ trợ nhiều kênh gửi thông báo, bạn phân tách logic tạo notifier khỏi logic gửi thông báo như thế nào?
Bạn lựa chọn interface sản phẩm đủ ổn định để thêm loại notifier mới mà không thay đổi client ra sao?
Khi thuật toán của Creator cần kiểm tra điều kiện trước khi tạo sản phẩm, bạn tổ chức phương thức template như thế nào?
Bạn xác minh rằng mỗi Concrete Creator trả về sản phẩm tương thích với các invariant mà Creator yêu cầu ra sao?
Khi Concrete Product có hành vi khác nhau ngoài hợp đồng chung, bạn ngăn client phụ thuộc vào kiểu cụ thể như thế nào?
Bạn sẽ phát hiện hành vi nào trong lớp con vi phạm nguyên tắc thay thế Liskov khi mở rộng Factory Method?
Bạn đánh giá việc trả về interface so với lớp cụ thể ảnh hưởng đến khả năng thay thế triển khai ra sao?
Khi có hàng chục biến thể dựa trên dữ liệu cấu hình, bạn nhận diện giới hạn của việc tạo subclass cho mỗi biến thể như thế nào?
Bạn áp dụng registry chứa nhiều factory để chọn triển khai tại runtime khi yêu cầu thay đổi linh hoạt ra sao?
Bạn sẽ kiểm soát khóa đăng ký trùng hoặc không tồn tại trong một factory registry như thế nào?
Bạn phân biệt lựa chọn Concrete Creator lúc khởi động với lựa chọn theo từng request trong thiết kế như thế nào?
Khi cần tạo sản phẩm dựa trên quyền người dùng, bạn đặt logic phân quyền ở đâu để tránh lẫn với khởi tạo đối tượng?
Bạn đánh giá Factory Method có giúp tách phần phụ thuộc hạ tầng khỏi domain trong kiến trúc Java như thế nào?
Khi framework dependency injection đã tạo đối tượng, bạn xác định nhu cầu Factory Method còn lại là gì?
Bạn sẽ kết hợp Factory Method với dependency injection để hỗ trợ nhiều triển khai Product như thế nào?
Khi cấu hình được tải lại trong lúc hệ thống chạy, bạn bảo đảm việc chọn factory nhất quán như thế nào?
Bạn giải quyết vấn đề an toàn luồng khi nhiều request gọi chung một Concrete Creator có trạng thái mutable ra sao?
Nếu khởi tạo sản phẩm tốn thời gian, bạn lựa chọn tạo mới, lazy initialization hay reuse theo tiêu chí nào?
Bạn tổ chức kiểm thử Creator độc lập với Concrete Product bằng test double như thế nào?
Bạn kiểm thử các nhánh tạo sản phẩm và hành vi trả lỗi của một factory method bằng những tình huống nào?
Khi thêm Concrete Product mới, bạn dùng contract test nào để xác minh tuân thủ hợp đồng Product?
Bạn kiểm tra việc Factory Method có vô tình gây side effect tại thời điểm khởi tạo bằng cách nào?
Bạn lựa chọn cách ghi log hoặc theo dõi lỗi tạo sản phẩm mà không đưa chi tiết triển khai vào mã nghiệp vụ ra sao?
Khi di chuyển mã đang dùng new trong nhiều vị trí sang Factory Method, bạn tổ chức từng bước refactor như thế nào?
Bạn đánh giá nguy cơ thay đổi hành vi khi chuyển từ tạo trực tiếp sang sản phẩm qua interface bằng những kiểm thử nào?
Bạn chỉ ra trường hợp nào một constructor hoặc static factory đơn giản vẫn dễ bảo trì hơn hệ phân cấp Creator?
Khi các Concrete Creator lặp lại nhiều đoạn khởi tạo giống nhau, bạn thiết kế điểm dùng chung nào để giảm trùng lặp?
Bạn dùng những tín hiệu thực tế nào để quyết định áp dụng, giữ lại hoặc loại bỏ Factory Method khỏi một thiết kế?
