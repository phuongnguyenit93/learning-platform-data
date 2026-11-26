Bạn sẽ giải thích mục tiêu của Clean Architecture và vấn đề bảo trì nào nó cố gắng giải quyết như thế nào?
Bạn sẽ mô tả Dependency Rule và xác định hướng phụ thuộc hợp lệ giữa các tầng của hệ thống ra sao?
Bạn sẽ phân biệt phụ thuộc ở thời điểm biên dịch với hướng dữ liệu chạy qua các thành phần như thế nào?
Bạn sẽ xác định chính sách nghiệp vụ cốt lõi nào cần tồn tại độc lập với framework và cơ sở dữ liệu ra sao?
Bạn sẽ phân biệt entity trong Clean Architecture với entity dùng để ánh xạ bảng trong ORM như thế nào?
Khi thiết kế một entity miền, bạn sẽ đặt những bất biến và quy tắc nghiệp vụ nào ngay trong đối tượng?
Bạn sẽ xác định trách nhiệm của use case và phân biệt nó với thao tác CRUD đơn giản như thế nào?
Với quy trình đặt hàng, bạn sẽ tách phần quyết định nghiệp vụ khỏi việc đọc ghi dữ liệu và gửi thông báo ra sao?
Bạn sẽ thiết kế đầu vào và đầu ra của một use case sao cho không phụ thuộc vào HTTP hoặc kiểu dữ liệu của framework như thế nào?
Bạn sẽ phân biệt input boundary, output boundary và adapter khi theo dõi một yêu cầu từ giao diện tới miền nghiệp vụ ra sao?
Bạn sẽ giải thích vai trò của controller trong việc chuyển dữ liệu từ request thành lời gọi use case như thế nào?
Bạn sẽ thiết kế presenter hoặc output adapter để cùng một kết quả use case có thể hiển thị trên web và CLI ra sao?
Bạn sẽ xác định khi nào cần DTO riêng cho request, use case và response thay vì tái sử dụng một lớp dữ liệu như thế nào?
Khi hai tầng có mô hình dữ liệu khác nhau, bạn sẽ tổ chức việc ánh xạ để không rò rỉ chi tiết của tầng ngoài vào tầng trong ra sao?
Bạn sẽ thiết kế một interface gateway cho việc lấy dữ liệu khách hàng theo ngôn ngữ nghiệp vụ thay vì ngôn ngữ SQL như thế nào?
Bạn sẽ quyết định interface thuộc tầng use case hay adapter dựa trên hướng phụ thuộc và bên sở hữu nhu cầu ra sao?
Bạn sẽ giải thích cách Dependency Inversion cho phép use case dùng kho dữ liệu mà không import thư viện persistence như thế nào?
Bạn sẽ triển khai repository adapter cho cơ sở dữ liệu quan hệ mà không để loại entity ORM đi qua boundary như thế nào?
Khi cần chuyển cơ sở dữ liệu hoặc dịch vụ bên ngoài, bạn sẽ chỉ ra những lớp nào được phép thay đổi và những lớp nào phải giữ nguyên ra sao?
Bạn sẽ thiết kế adapter cho API thanh toán bên thứ ba sao cho thay đổi giao thức không làm đổi quy tắc thanh toán như thế nào?
Bạn sẽ lựa chọn vị trí đặt validation cú pháp đầu vào so với validation quy tắc nghiệp vụ trong Clean Architecture ra sao?
Khi cần xác thực và phân quyền người dùng, bạn sẽ phân biệt chính sách truy cập nghiệp vụ với chi tiết token hoặc middleware như thế nào?
Bạn sẽ phân tích vì sao use case không nên trực tiếp tạo kết nối cơ sở dữ liệu hoặc gọi phương thức của web framework ra sao?
Bạn sẽ xác định ranh giới transaction để use case nhiều bước vẫn bảo đảm tính nhất quán mà không phụ thuộc trực tiếp vào framework như thế nào?
Khi yêu cầu nghiệp vụ có tác vụ bất đồng bộ, bạn sẽ thiết kế boundary cho việc phát sự kiện hoặc gửi message như thế nào?
Bạn sẽ quyết định phần nào của logic retry hoặc timeout thuộc chính sách nghiệp vụ và phần nào thuộc adapter hạ tầng ra sao?
Bạn sẽ thiết kế cách truyền lỗi nghiệp vụ qua boundary mà không làm lộ exception riêng của cơ sở dữ liệu như thế nào?
Bạn sẽ tổ chức mapping giữa kết quả use case thất bại và mã phản hồi HTTP trong tầng nào, vì sao?
Bạn sẽ xác định vị trí xử lý ngày giờ và nguồn đồng hồ để có thể kiểm thử nghiệp vụ phụ thuộc thời gian như thế nào?
Bạn sẽ trừu tượng hóa việc sinh định danh hoặc giá trị ngẫu nhiên mà vẫn giữ use case dễ kiểm thử ra sao?
Bạn sẽ giải thích composition root làm nhiệm vụ kết nối các interface với implementation vào thời điểm khởi tạo như thế nào?
Bạn sẽ chọn phương thức dependency injection nào để giữ phụ thuộc của use case rõ ràng và dễ nhận biết như thế nào?
Bạn sẽ phát hiện dấu hiệu service locator hoặc truy cập global state khiến kiến trúc khó kiểm thử bằng cách nào?
Bạn sẽ thiết kế cấu trúc package hoặc module để phản ánh use case và hạn chế phụ thuộc sai tầng ra sao?
Khi một interface bị dùng bởi quá nhiều use case với nhu cầu khác nhau, bạn sẽ chia nhỏ abstraction theo tiêu chí nào?
Bạn sẽ phân biệt một boundary ổn định với abstraction được tạo quá sớm khiến mã nguồn phức tạp không cần thiết như thế nào?
Bạn sẽ xác định khi nào nên dùng Clean Architecture đầy đủ và khi nào giải pháp đơn giản hơn là đủ như thế nào?
Bạn sẽ kiểm thử entity thuần nghiệp vụ mà không khởi động cơ sở dữ liệu hay framework bằng cách nào?
Bạn sẽ thiết kế kiểm thử use case với gateway giả lập để kiểm tra cả kết quả lẫn các tương tác quan trọng như thế nào?
Bạn sẽ xây dựng kiểm thử tích hợp cho adapter persistence để kiểm tra ánh xạ dữ liệu thực ra sao?
Bạn sẽ kiểm tra controller và presenter thực hiện đúng phép chuyển đổi dữ liệu ở hai đầu boundary như thế nào?
Bạn sẽ xác định phần nào cần kiểm thử hợp đồng giữa port và adapter để tránh triển khai adapter sai kỳ vọng như thế nào?
Bạn sẽ áp dụng quy tắc kiểm tra phụ thuộc tự động để ngăn tầng nghiệp vụ import tầng hạ tầng như thế nào?
Khi một nhóm muốn gọi framework trực tiếp trong use case cho tiện, bạn sẽ đánh giá hệ quả và lựa chọn thay thế ra sao?
Bạn sẽ lập kế hoạch tách dần nghiệp vụ khỏi controller lớn của hệ thống hiện có mà không làm hỏng chức năng như thế nào?
Khi chuyển các thao tác truy vấn dữ liệu sang adapter, bạn sẽ giữ nguyên hành vi nghiệp vụ và hiệu năng quan sát được như thế nào?
Bạn sẽ dùng seam và kiểm thử hồi quy để thực hiện tái cấu trúc từng bước thay vì viết lại toàn bộ hệ thống ra sao?
Bạn sẽ phân tích chi phí chuyển đổi dữ liệu, số lượng lớp và mức độ gián tiếp khi đánh giá hiệu quả của Clean Architecture như thế nào?
Bạn sẽ nhận diện tình huống một use case trở thành lớp trung gian chỉ chuyển tiếp lời gọi và quyết định cách cải tiến ra sao?
Khi yêu cầu mở rộng sang giao diện mới hoặc thay framework, bạn sẽ đánh giá bằng chứng nào cho thấy boundary đã được thiết kế đúng?
