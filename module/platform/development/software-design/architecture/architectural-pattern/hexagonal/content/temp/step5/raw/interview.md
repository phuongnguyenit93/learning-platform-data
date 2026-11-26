Bạn sẽ giải thích mục tiêu của Hexagonal Architecture khi tách nghiệp vụ khỏi database, giao diện và framework như thế nào?
Bạn sẽ xác định phần nào của một ứng dụng Java cần nằm trong lõi domain và use case ra sao?
Bạn sẽ phân biệt inbound port, outbound port và adapter qua một chức năng đặt hàng cụ thể như thế nào?
Bạn sẽ mô tả đường đi của một yêu cầu HTTP từ adapter đầu vào đến use case rồi ra adapter lưu trữ như thế nào?
Bạn sẽ thiết kế inbound port để mô tả ý định nghiệp vụ mà không phụ thuộc vào kiểu request của Spring như thế nào?
Bạn sẽ xác định ranh giới giữa domain entity, application service và adapter khi xử lý một quy tắc nghiệp vụ ra sao?
Bạn sẽ áp dụng nguyên tắc đảo ngược phụ thuộc để lõi nghiệp vụ không phải import lớp của tầng hạ tầng như thế nào?
Bạn sẽ đặt interface của outbound port ở đâu để domain và use case có thể được kiểm thử độc lập ra sao?
Bạn sẽ chọn mức độ chi tiết của các thao tác trong outbound port dựa trên nhu cầu use case như thế nào?
Bạn sẽ phân biệt outbound port dành cho lưu trữ dữ liệu với port dành cho gửi thông báo hoặc gọi dịch vụ ngoài ra sao?
Bạn sẽ thiết kế adapter JPA để triển khai port lưu trữ mà không làm lộ entity persistence vào lõi như thế nào?
Bạn sẽ chuyển đổi giữa domain model và JPA entity tại ranh giới adapter để tránh rò rỉ chi tiết hạ tầng ra sao?
Bạn sẽ thiết kế adapter cho REST API và một tác vụ chạy theo lịch cùng gọi một inbound port như thế nào?
Bạn sẽ xử lý yêu cầu gọi cùng use case từ giao diện web và hệ thống gửi thông điệp mà vẫn thống nhất quy tắc nghiệp vụ ra sao?
Bạn sẽ quyết định khi nào một interface thực sự là port và khi nào chỉ là lớp trừu tượng không có giá trị kiến trúc như thế nào?
Bạn sẽ tránh tình trạng mỗi lớp đều có một interface khiến số lượng port tăng mà không rõ mục đích như thế nào?
Bạn sẽ thiết kế dữ liệu đầu vào và đầu ra của use case để không phụ thuộc vào HTTP status hay cấu trúc JSON như thế nào?
Bạn sẽ đặt validation cú pháp, validation dữ liệu và kiểm tra bất biến nghiệp vụ ở đâu trong kiến trúc hexagonal ra sao?
Bạn sẽ phân biệt lỗi nghiệp vụ với lỗi kỹ thuật khi một outbound adapter gọi dịch vụ khác thất bại như thế nào?
Bạn sẽ chuyển lỗi từ use case thành HTTP response ở adapter đầu vào mà không đưa khái niệm HTTP vào domain ra sao?
Bạn sẽ xác định ai sở hữu ranh giới transaction khi một use case ghi nhiều dữ liệu thông qua các outbound port như thế nào?
Bạn sẽ xử lý yêu cầu cập nhật dữ liệu và gửi sự kiện mà hai thao tác không thể dùng chung một transaction ra sao?
Bạn sẽ thiết kế port cho hệ thống thanh toán bên ngoài sao cho việc thay nhà cung cấp không làm thay đổi quy tắc đặt hàng như thế nào?
Bạn sẽ thay một adapter thật bằng fake hoặc in-memory adapter để kiểm thử luồng nghiệp vụ như thế nào?
Bạn sẽ viết unit test cho use case bằng các port giả lập mà không cần khởi động Spring hay cơ sở dữ liệu ra sao?
Bạn sẽ thiết kế test xác minh adapter JPA thực thi đúng hợp đồng của outbound port như thế nào?
Bạn sẽ kiểm chứng adapter HTTP ánh xạ request, lỗi và response đúng mà không kiểm thử lặp lại toàn bộ logic nghiệp vụ ra sao?
Bạn sẽ phân biệt unit test của lõi, contract test cho port và integration test của adapter theo mức độ rủi ro ra sao?
Bạn sẽ tổ chức package hoặc module Java để ngăn dependency từ domain đến Spring MVC hay JPA như thế nào?
Bạn sẽ áp dụng kiểm tra kiến trúc tự động để phát hiện import vi phạm chiều phụ thuộc ra sao?
Bạn sẽ xác định trường hợp framework annotation có thể khiến domain bị ràng buộc với hạ tầng như thế nào?
Bạn sẽ dùng dependency injection của Spring ở composition root để liên kết port với adapter cụ thể ra sao?
Bạn sẽ thiết kế cấu hình để chọn adapter giả lập, adapter thật hoặc adapter dự phòng ở những môi trường khác nhau như thế nào?
Bạn sẽ kiểm soát việc adapter gọi ngược vào lớp triển khai use case khiến ranh giới và trách nhiệm bị lẫn lộn ra sao?
Bạn sẽ mô hình hóa tương tác bất đồng bộ bằng inbound adapter nhận sự kiện và outbound port công bố sự kiện như thế nào?
Bạn sẽ xem xét idempotency và xử lý lặp thông điệp ở đâu khi một use case được kích hoạt từ message broker ra sao?
Bạn sẽ xác định cách truyền thông tin người dùng và quyền truy cập đến use case mà không làm domain phụ thuộc vào Spring Security như thế nào?
Bạn sẽ đặt cơ chế logging, tracing và metric ở đâu để quan sát luồng xử lý mà không làm ô nhiễm nghiệp vụ như thế nào?
Bạn sẽ quản lý timeout và retry khi adapter gọi một dịch vụ bên ngoài mà không che giấu kết quả thất bại khỏi use case ra sao?
Bạn sẽ quyết định khi nào cần cache ở adapter và cách tránh để hành vi cache làm sai bất biến nghiệp vụ như thế nào?
Bạn sẽ tổ chức một ứng dụng có nhiều bounded context để tránh dùng chung port và domain model thiếu kiểm soát như thế nào?
Bạn sẽ đánh giá nguy cơ use case trở thành lớp điều phối khổng lồ chứa cả logic hạ tầng và logic domain như thế nào?
Bạn sẽ phân biệt Hexagonal Architecture với Layered Architecture dựa trên ranh giới phụ thuộc và khả năng thay adapter ra sao?
Bạn sẽ xem xét khi nào kiến trúc hexagonal tạo thêm chi phí không cần thiết cho một ứng dụng Java nhỏ như thế nào?
Bạn sẽ xác định những điểm phụ thuộc hạ tầng cần tách đầu tiên khi chuyển một ứng dụng Spring MVC/JPA hiện có sang hexagonal ra sao?
Bạn sẽ xây dựng kế hoạch chuyển từng chức năng sang ports và adapters mà vẫn duy trì tương thích với API hiện tại như thế nào?
Bạn sẽ dùng characterization test để bảo vệ hành vi trước khi di chuyển logic nghiệp vụ ra khỏi controller hoặc repository ra sao?
Bạn sẽ tổ chức việc thay dần adapter cũ bằng adapter mới mà các use case khác vẫn hoạt động như thế nào?
Bạn sẽ đánh giá thành công của việc áp dụng hexagonal qua khả năng kiểm thử, thay đổi hạ tầng và số vi phạm phụ thuộc ra sao?
Bạn sẽ xử lý tình huống nhóm phát hiện domain đang import hàng loạt lớp Spring Data ngay trước khi thay cơ sở dữ liệu như thế nào?
