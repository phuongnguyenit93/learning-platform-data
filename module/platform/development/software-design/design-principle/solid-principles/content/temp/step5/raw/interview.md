Bạn giải thích mục tiêu chung của năm nguyên lý SOLID đối với khả năng thay đổi và kiểm thử mã hướng đối tượng như thế nào?
Khi một lớp Java trở nên khó bảo trì, bạn dùng dấu hiệu nào để xác định nguyên lý SOLID có thể đang bị vi phạm?
Bạn phân biệt Single Responsibility Principle với quy tắc mỗi lớp chỉ được có một phương thức như thế nào?
Bạn xác định một lý do thay đổi độc lập của lớp dựa trên các bên liên quan và yêu cầu nghiệp vụ ra sao?
Nếu một lớp OrderService vừa tính giá, lưu database và gửi email, bạn phân tích các tác nhân thay đổi khác nhau như thế nào?
Bạn sẽ tách một lớp vừa định dạng báo cáo vừa tính số liệu mà không làm phân tán quy tắc nghiệp vụ ra sao?
Khi hai phương thức thường thay đổi cùng nhau, bạn dùng dữ kiện nào để quyết định giữ chung hay tách trách nhiệm?
Bạn nhận diện trường hợp áp dụng SRP quá mức khiến một use case phải đi qua quá nhiều lớp như thế nào?
Bạn lựa chọn bộ kiểm thử nào để bảo đảm refactor theo SRP không làm thay đổi hành vi hiện có?
Bạn phân biệt SRP với Separation of Concerns trong việc xác định ranh giới lớp và module như thế nào?
Open/Closed Principle định hướng cách mở rộng hành vi của một thành phần mà không liên tục sửa mã ổn định như thế nào?
Khi một phương thức chứa chuỗi if theo loại phương thức thanh toán, bạn đánh giá nên dùng polymorphism ra sao?
Bạn thiết kế hợp đồng cho chiến lược tính phí để bổ sung biến thể mà không thay đổi mã điều phối như thế nào?
Khi một yêu cầu mới làm thay đổi invariant của mọi biến thể, bạn phân biệt sửa hợp đồng chung với mở rộng triển khai ra sao?
Bạn sẽ chọn điểm mở rộng nào để tránh tạo interface chỉ phục vụ một khả năng thay đổi chưa có bằng chứng?
Bạn so sánh plugin registry, composition và inheritance trong việc áp dụng OCP cho các biến thể nghiệp vụ như thế nào?
Khi thêm một loại thông báo mới, bạn thiết kế kiểm thử chứng minh logic gửi chung không cần sửa ra sao?
Bạn đánh giá rủi ro của hệ phân cấp lớp phức tạp chỉ để tránh một câu lệnh điều kiện đơn giản như thế nào?
Bạn xác định phần mã nào nên được giữ ổn định và phần nào thực sự thay đổi thường xuyên để áp dụng OCP ra sao?
Liskov Substitution Principle yêu cầu những bảo đảm nào khi đối tượng lớp con thay thế lớp cha?
Bạn xây dựng ví dụ nào cho thấy một lớp con ném UnsupportedOperationException làm hỏng kỳ vọng của client?
Vì sao việc lớp con tăng điều kiện tiên quyết so với hợp đồng lớp cha có thể phá vỡ client đang hoạt động đúng?
Khi lớp con trả về kết quả yếu hơn điều kiện hậu nghiệm của lớp cha, bạn sẽ phát hiện vi phạm LSP ra sao?
Bạn thiết kế contract test để cùng một bộ kiểm thử áp dụng được cho tất cả triển khai interface như thế nào?
Nếu một lớp Square kế thừa Rectangle có setter chiều rộng và chiều cao độc lập, bạn phân tích rủi ro thay thế ra sao?
Bạn xác định các invariant và tác dụng phụ phải được giữ lại khi override một phương thức như thế nào?
Khi hai kiểu dữ liệu có cấu trúc tương tự nhưng hành vi khác nhau, bạn quyết định dùng composition thay inheritance ra sao?
Bạn phân biệt lỗi thay thế do hợp đồng thiết kế sai với lỗi hiện thực của một lớp con bằng cách nào?
Interface Segregation Principle giải quyết vấn đề gì khi client bị buộc phụ thuộc vào những phương thức không sử dụng?
Bạn sẽ phát hiện một interface quản lý tài liệu chứa thao tác đọc, ghi, in và ký đang gây khó cho client nào?
Bạn chia một interface lớn thành các hợp đồng theo năng lực mà vẫn tránh phân mảnh API như thế nào?
Khi một triển khai phải trả lỗi cho nhiều phương thức không hỗ trợ, bạn đánh giá ranh giới interface ra sao?
Bạn phân biệt interface phục vụ vai trò của client với interface phân chia thuần theo thao tác CRUD như thế nào?
Bạn sử dụng adapter để hỗ trợ client cũ khi tách interface lớn mà vẫn giữ khả năng tương thích ra sao?
Bạn sẽ kiểm tra mức ghép nối của một client chỉ cần đọc dữ liệu trước và sau khi áp dụng ISP như thế nào?
Bạn đánh giá chi phí của quá nhiều interface nhỏ lên khả năng khám phá và sử dụng API như thế nào?
Dependency Inversion Principle phát biểu mối quan hệ phụ thuộc giữa chính sách nghiệp vụ và chi tiết hạ tầng ra sao?
Bạn phân biệt dependency inversion với dependency injection và giải thích cách hai kỹ thuật phối hợp như thế nào?
Khi domain service trực tiếp tạo JDBC repository bằng new, bạn sẽ đảo chiều phụ thuộc từng bước như thế nào?
Bạn lựa chọn vị trí định nghĩa interface repository để chính sách nghiệp vụ không phụ thuộc vào database cụ thể ra sao?
Bạn dùng constructor injection để thể hiện dependency bắt buộc và hỗ trợ kiểm thử độc lập như thế nào?
Nếu một interface hạ tầng chỉ sao chép nguyên xi API của thư viện bên ngoài, bạn đánh giá chất lượng abstraction ra sao?
Bạn thiết kế adapter thay thế nhà cung cấp email mà không sửa logic use case theo DIP như thế nào?
Bạn phân biệt composition root với service locator toàn cục dựa trên tính minh bạch của dependency ra sao?
Khi framework DI tự tạo object graph, bạn làm thế nào để kiểm tra phụ thuộc vòng và vòng đời thành phần?
Bạn xây dựng quy trình refactor cho một lớp vi phạm đồng thời SRP, ISP và DIP theo thứ tự ưu tiên nào?
Bạn dùng unit test, integration test và contract test để chứng minh các abstraction sau refactor còn đúng hành vi ra sao?
Khi SOLID làm tăng số lớp và độ gián tiếp, bạn chọn chỉ số và bằng chứng nào để cân nhắc chi phí bảo trì?
Bạn xử lý trường hợp áp dụng OCP gây xung đột với nhu cầu đơn giản hóa theo SRP và ISP như thế nào?
Khi code review một thay đổi liên quan nhiều lớp, bạn sẽ đặt những câu hỏi nào để đánh giá áp dụng SOLID thực sự có ích?
