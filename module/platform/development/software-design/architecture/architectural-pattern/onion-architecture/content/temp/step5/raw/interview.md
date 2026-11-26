Bạn giải thích nguyên tắc đặt domain model ở trung tâm của Onion Architecture bằng một bài toán nghiệp vụ cụ thể như thế nào?
Bạn phân biệt Onion Architecture với cách chia lớp controller, service và repository truyền thống dựa trên chiều phụ thuộc mã nguồn ra sao?
Bạn xác định những quy tắc nghiệp vụ nào nên thuộc domain thay vì application service khi bắt đầu thiết kế hệ thống như thế nào?
Bạn sử dụng những dấu hiệu nào để phát hiện domain model đang phụ thuộc vào framework hoặc cơ sở dữ liệu?
Bạn tổ chức các vòng phụ thuộc trong Onion Architecture để lớp bên ngoài có thể sử dụng lớp bên trong nhưng không xảy ra điều ngược lại như thế nào?
Bạn phân biệt sự phụ thuộc khi biên dịch với luồng gọi hàm lúc chạy trong kiến trúc có dependency inversion ra sao?
Khi một domain service cần tra cứu dữ liệu, bạn đặt interface ở lớp nào và giải thích lý do như thế nào?
Bạn thiết kế abstraction cho việc lưu trữ đơn hàng mà không làm lộ thuật ngữ SQL hoặc ORM vào domain ra sao?
Bạn phân biệt entity, value object và domain service qua trách nhiệm giữ bất biến nghiệp vụ như thế nào?
Bạn thiết kế một aggregate để bảo đảm trạng thái đơn hàng không thể chuyển sang trạng thái không hợp lệ ra sao?
Bạn xử lý quy tắc tính giá hoặc chiết khấu thay đổi thường xuyên mà không làm domain phụ thuộc vào API ngoài như thế nào?
Bạn xác định khi nào hành vi nghiệp vụ nên nằm trong entity thay vì được viết hết trong application service ra sao?
Bạn mô hình hóa domain exception để thể hiện lỗi nghiệp vụ mà không gắn vào mã trạng thái HTTP như thế nào?
Bạn phân biệt lỗi vi phạm bất biến domain với lỗi hạ tầng khi tổ chức xử lý ngoại lệ qua các lớp ra sao?
Bạn xác định đầu vào, đầu ra và trách nhiệm điều phối của một application use case như thế nào?
Bạn thiết kế use case tạo đơn hàng có nhiều bước mà vẫn tránh đưa quy tắc cốt lõi ra khỏi domain ra sao?
Bạn lựa chọn trả về domain object hay DTO từ application layer dựa trên nhu cầu kiểm soát ranh giới như thế nào?
Bạn xử lý mapping từ HTTP request sang application command rồi sang domain model ở những vị trí nào?
Bạn ngăn các annotation của ORM hoặc web framework lan vào những lớp domain nào và bằng cách nào?
Bạn dùng những tiêu chí nào để đánh giá annotation từ thư viện chung có làm suy giảm tính độc lập framework của domain?
Bạn thiết kế interface cho đồng hồ thời gian hoặc bộ sinh định danh khi domain cần những khả năng này ra sao?
Bạn sử dụng dependency inversion để thay một hệ quản trị cơ sở dữ liệu mà không chỉnh sửa quy tắc domain như thế nào?
Bạn tổ chức các implementation của repository, notification gateway và external client trong infrastructure layer ra sao?
Bạn phân biệt interface đại diện cho nhu cầu của use case với interface chỉ phản chiếu toàn bộ API của thư viện hạ tầng như thế nào?
Bạn nhận diện abstraction quá rộng khiến application layer vô tình phụ thuộc vào chi tiết triển khai như thế nào?
Bạn thiết lập dependency injection ở composition root để nối các interface bên trong với implementation bên ngoài ra sao?
Bạn xác định lớp nào nên quản lý transaction khi một use case phải ghi dữ liệu và gửi thông báo như thế nào?
Bạn phân tích giới hạn của một transaction cơ sở dữ liệu khi use case còn gọi dịch vụ bên ngoài ra sao?
Bạn thiết kế cơ chế phát domain event mà không buộc entity phải biết message broker cụ thể như thế nào?
Bạn lựa chọn đồng bộ hay bất đồng bộ cho một adapter gửi thông báo và làm rõ tác động đến hợp đồng use case ra sao?
Bạn xử lý timeout hoặc mất kết nối từ infrastructure để domain không bị trộn logic retry kỹ thuật như thế nào?
Bạn thiết kế giao diện repository để phục vụ truy vấn nghiệp vụ mà không đưa cú pháp lọc của ORM vào trong như thế nào?
Bạn cân nhắc đặt những truy vấn báo cáo phức tạp ngoài domain khi chúng không thể hiện quy tắc nghiệp vụ ra sao?
Bạn ngăn domain model trở thành mô hình dữ liệu nghèo hành vi chỉ chứa getter và setter bằng biện pháp nào?
Bạn nhận diện application service quá lớn đang tích tụ logic domain qua những dấu hiệu gì?
Bạn áp dụng quy tắc phụ thuộc hướng vào trong ở cấp package hoặc module bằng cấu trúc mã nguồn như thế nào?
Bạn thiết kế kiểm tra kiến trúc tự động để phát hiện package domain import các lớp web hoặc persistence ra sao?
Bạn đặt các interface ở những module nào để tránh vòng phụ thuộc khi chia application thành nhiều project xây dựng độc lập?
Bạn so sánh mức độ linh hoạt khi thay UI web bằng CLI trong kiến trúc Onion với kiến trúc gắn logic vào controller như thế nào?
Bạn kiểm thử một entity và các bất biến bằng unit test thuần Java mà không khởi động framework ra sao?
Bạn sử dụng fake repository khi kiểm thử một application use case và xác định giới hạn của fake như thế nào?
Bạn lựa chọn kiểm thử integration nào để xác nhận adapter persistence thực hiện đúng hợp đồng interface ra sao?
Bạn xây dựng contract test cho hai implementation khác nhau của cùng gateway để bảo đảm cùng ý nghĩa nghiệp vụ như thế nào?
Bạn quyết định thành phần nào được mock và thành phần nào phải chạy thật khi kiểm thử xuyên qua domain, application và infrastructure ra sao?
Bạn thiết kế một use case để dễ kiểm tra nhánh thành công, vi phạm quy tắc và lỗi hạ tầng riêng biệt như thế nào?
Bạn phân tích chi phí thêm interface và lớp adapter đối với một ứng dụng nhỏ có yêu cầu ít thay đổi ra sao?
Bạn lựa chọn mức độ tách lớp hợp lý để không biến Onion Architecture thành nhiều wrapper chỉ truyền tham số như thế nào?
Bạn chuyển một ứng dụng Java đang để SQL trong service sang cấu trúc Onion theo các bước ít rủi ro như thế nào?
Bạn bảo vệ hành vi hiện có bằng kiểm thử ra sao khi di chuyển quy tắc nghiệp vụ ra khỏi controller hoặc repository?
Bạn xử lý việc domain và persistence có cách biểu diễn quan hệ khác nhau mà không làm rò rỉ mô hình ORM ra sao?
Bạn xác định thời điểm dùng domain model riêng với persistence model thay vì ánh xạ chung một lớp theo tiêu chí nào?
Bạn thiết kế quy ước đặt tên package và interface để người mới nhìn vào có thể nhận ra hướng phụ thuộc như thế nào?
Bạn đánh giá liệu thay đổi framework web có còn buộc sửa domain hay không bằng cách kiểm tra những điểm tiếp xúc nào?
Bạn dùng những tín hiệu nào về khả năng kiểm thử, tốc độ thay đổi và số phụ thuộc để đánh giá Onion Architecture đang mang lại lợi ích thực tế?
