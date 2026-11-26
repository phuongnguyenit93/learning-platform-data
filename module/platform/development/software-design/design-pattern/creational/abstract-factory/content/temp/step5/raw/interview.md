Bạn sẽ giải thích Abstract Factory giải quyết vấn đề gì khi một hệ thống phải tạo nhiều đối tượng thuộc cùng một họ sản phẩm?
Bạn sẽ phân biệt việc tạo một đối tượng riêng lẻ với việc tạo một bộ sản phẩm có quan hệ tương thích như thế nào?
Bạn sẽ mô tả vai trò của Abstract Factory, Concrete Factory, Abstract Product và Concrete Product trong mẫu thiết kế này ra sao?
Bạn sẽ xác định đâu là một họ sản phẩm khi phân tích yêu cầu giao diện có nhiều chủ đề hoặc nền tảng khác nhau như thế nào?
Trong ứng dụng hỗ trợ hai bộ giao diện, bạn sẽ thiết kế factory tạo nút bấm và hộp thoại cùng phong cách ra sao?
Bạn sẽ xác định các hợp đồng sản phẩm cần ổn định để client không phụ thuộc vào lớp triển khai cụ thể như thế nào?
Bạn sẽ thiết kế interface của Abstract Factory gồm những phương thức tạo sản phẩm nào mà không đưa chi tiết nền tảng vào?
Khi một Concrete Factory trả về nhiều sản phẩm, bạn sẽ bảo đảm chúng thuộc cùng một họ tương thích như thế nào?
Bạn sẽ tổ chức cách client nhận factory và sử dụng sản phẩm mà không gọi trực tiếp constructor của lớp cụ thể ra sao?
Bạn sẽ lựa chọn factory theo cấu hình ứng dụng vào thời điểm khởi tạo bằng quy trình nào?
Nếu người dùng thay đổi chủ đề giao diện trong lúc chạy, bạn sẽ quản lý việc tạo lại các sản phẩm liên quan như thế nào?
Bạn sẽ xử lý tình huống không có Concrete Factory ứng với cấu hình được yêu cầu để tránh trả về đối tượng sai như thế nào?
Bạn sẽ phân biệt Abstract Factory với Factory Method về mục đích tạo họ sản phẩm và điểm mở rộng ra sao?
Bạn sẽ so sánh Abstract Factory với Builder khi việc tạo đối tượng có nhiều bước cấu hình nhưng không có nhiều họ sản phẩm như thế nào?
Bạn sẽ đánh giá lúc nào dùng dependency injection thông thường đã đủ và không cần xây dựng Abstract Factory riêng ra sao?
Bạn sẽ sử dụng composition thay cho việc để client kế thừa một factory để giảm phụ thuộc vào cách khởi tạo như thế nào?
Khi các sản phẩm có interface giống nhau nhưng hành vi khác theo môi trường, bạn sẽ định nghĩa phần hợp đồng chung ra sao?
Bạn sẽ tránh việc một Concrete Factory tạo ra tổ hợp sản phẩm không tương thích với nhau bằng những quy tắc thiết kế nào?
Bạn sẽ xác định nơi đặt logic chọn factory để không rải các nhánh điều kiện về loại sản phẩm khắp hệ thống như thế nào?
Bạn sẽ thiết kế một registry hoặc cấu hình ánh xạ tên họ sản phẩm sang factory mà vẫn phát hiện thiếu cấu hình ra sao?
Khi một họ sản phẩm cần cấu hình riêng, bạn sẽ truyền tham số cho factory mà không làm rò rỉ chi tiết ấy vào client như thế nào?
Bạn sẽ cân nhắc constructor injection, phương thức tạo có tham số và đối tượng cấu hình khi sản phẩm cần dữ liệu đầu vào ra sao?
Bạn sẽ xác định khi nào factory nên trả đối tượng mới mỗi lần và khi nào có thể tái sử dụng một thể hiện đã tạo như thế nào?
Khi sản phẩm giữ trạng thái có thể thay đổi, bạn sẽ phân tích nguy cơ chia sẻ cùng một thể hiện giữa nhiều client ra sao?
Bạn sẽ kiểm soát việc tạo factory và sản phẩm trong môi trường đa luồng để tránh xung đột trạng thái như thế nào?
Khi sản phẩm sử dụng tài nguyên như kết nối hoặc tệp, bạn sẽ xác định trách nhiệm đóng tài nguyên thuộc factory hay client ra sao?
Bạn sẽ thiết kế cách báo lỗi tạo sản phẩm khi thiếu phụ thuộc mà không che giấu nguyên nhân của thất bại như thế nào?
Khi một Concrete Factory cần thực hiện khởi tạo chậm, bạn sẽ đánh giá tác động tới vòng đời và khả năng phát hiện lỗi sớm ra sao?
Bạn sẽ mở rộng hệ thống thêm một họ sản phẩm mới mà giữ nguyên mã client dựa trên những điều kiện nào?
Khi thêm một loại sản phẩm mới vào tất cả các họ, bạn sẽ phân tích số interface và Concrete Factory phải thay đổi như thế nào?
Bạn sẽ giải thích vì sao Abstract Factory phù hợp hơn khi các họ sản phẩm thay đổi thường xuyên hơn danh mục sản phẩm như thế nào?
Nếu một họ không hỗ trợ một loại sản phẩm bắt buộc, bạn sẽ chọn thay đổi hợp đồng, tách họ hay báo lỗi dựa trên tiêu chí nào?
Bạn sẽ nhận biết một Abstract Factory trở nên quá lớn vì chứa các sản phẩm không liên quan và cách phân tách ra sao?
Bạn sẽ cân nhắc sử dụng interface nhỏ hoặc nhiều factory phối hợp thay vì một factory khổng lồ theo nguyên tắc nào?
Bạn sẽ thiết kế quy ước đặt tên các Concrete Factory để phản ánh sự khác nhau giữa các họ mà không gắn cứng client vào công nghệ ra sao?
Bạn sẽ kiểm thử từng Concrete Factory để xác nhận đúng loại sản phẩm và các thuộc tính được cấu hình như thế nào?
Bạn sẽ xây dựng một bộ test hợp đồng dùng chung cho mọi factory để kiểm tra chúng cung cấp đầy đủ sản phẩm tương thích ra sao?
Bạn sẽ kiểm thử tương tác giữa hai sản phẩm trong cùng một họ để phát hiện lỗi không thể thấy khi kiểm tra chúng riêng lẻ như thế nào?
Bạn sẽ sử dụng factory giả lập trong unit test để tách client khỏi chi phí khởi tạo các sản phẩm thật ra sao?
Bạn sẽ kiểm tra logic chọn factory theo cấu hình hợp lệ, cấu hình thiếu và giá trị không được hỗ trợ như thế nào?
Khi muốn thay đổi bộ sản phẩm đang dùng, bạn sẽ bảo vệ client khỏi việc giữ tham chiếu trộn giữa họ cũ và họ mới như thế nào?
Bạn sẽ xác định cách kiểm thử lỗi khởi tạo giữa chừng khi factory đã tạo một số sản phẩm nhưng chưa hoàn thành toàn bộ họ ra sao?
Bạn sẽ đo chi phí tạo factory và sản phẩm thực tế trước khi quyết định tối ưu cache bằng phương pháp nào?
Bạn sẽ phân tích sự khác biệt giữa Abstract Factory và Strategy khi một mẫu tạo đối tượng còn mẫu kia thay thế hành vi ra sao?
Bạn sẽ so sánh Abstract Factory với Prototype trong trường hợp sản phẩm được tạo bằng sao chép thay vì khởi tạo trực tiếp như thế nào?
Khi refactor mã có nhiều câu lệnh new phụ thuộc môi trường, bạn sẽ chuyển dần sang Abstract Factory mà vẫn giữ hành vi cũ ra sao?
Bạn sẽ nhận diện dấu hiệu factory chỉ bọc một constructor đơn giản và khiến hệ thống phức tạp hơn lợi ích như thế nào?
Bạn sẽ thiết kế cơ chế kiểm soát phụ thuộc giữa module chứa hợp đồng sản phẩm và module chứa các Concrete Factory ra sao?
Bạn sẽ đánh giá tác động của việc thay thế toàn bộ họ sản phẩm lên khả năng mở rộng, kiểm thử và triển khai ứng dụng như thế nào?
Bạn sẽ xác định tiêu chí nào để kết luận Abstract Factory đã giảm kết dính và tăng khả năng thay đổi so với thiết kế ban đầu?
