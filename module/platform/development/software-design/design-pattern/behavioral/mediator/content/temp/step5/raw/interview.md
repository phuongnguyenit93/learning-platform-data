Bạn giải thích mục đích của mẫu thiết kế Mediator trong việc giảm sự phụ thuộc trực tiếp giữa các đối tượng cộng tác như thế nào?
Bạn nhận diện những dấu hiệu nào trong một nhóm đối tượng liên tục gọi lẫn nhau cho thấy nên cân nhắc Mediator?
Bạn phân biệt vai trò Mediator, ConcreteMediator và các Colleague trong một thiết kế điển hình ra sao?
Bạn mô tả luồng trao đổi thông tin khi một Colleague phát sinh sự kiện và Mediator quyết định phản ứng của các Colleague khác như thế nào?
Bạn thiết kế một form có nhiều ô nhập, nút xác nhận và thông báo lỗi bằng Mediator để tránh các thành phần UI phụ thuộc lẫn nhau ra sao?
Bạn xác định trách nhiệm phối hợp nào nên chuyển vào Mediator và hành vi nội tại nào vẫn phải nằm trong từng Colleague?
Bạn phân biệt Mediator với việc chỉ tạo một lớp chứa danh sách tất cả đối tượng và gọi hộ phương thức như thế nào?
Bạn lựa chọn giao diện Mediator tối thiểu để các Colleague chỉ biết những thao tác phối hợp cần thiết ra sao?
Bạn quyết định dùng thông báo sự kiện tổng quát hay các phương thức có tên nghiệp vụ rõ ràng trong Mediator dựa trên tiêu chí nào?
Bạn thiết kế payload của một thông báo gửi tới Mediator để đủ ngữ cảnh nhưng không làm lộ chi tiết riêng tư của Colleague ra sao?
Bạn bảo đảm một Colleague có thể được thay thế bằng phiên bản khác mà không bắt buộc sửa các Colleague còn lại như thế nào?
Bạn phân tích số lượng quan hệ phụ thuộc thay đổi ra sao khi chuyển từ các lời gọi ngang hàng sang thông qua Mediator?
Bạn so sánh Mediator với Observer về cách điều phối phản ứng và mức hiểu biết của bên gửi đối với bên nhận như thế nào?
Bạn phân biệt Mediator với Facade về hướng giao tiếp, vị trí sử dụng và trách nhiệm của lớp trung gian ra sao?
Bạn lựa chọn Mediator hay Chain of Responsibility khi nhiều thành phần cần xử lý một yêu cầu theo những cách khác nhau như thế nào?
Bạn nhận diện điểm khác nhau giữa Mediator và một event bus khi cần điều phối một tập đối tượng trong cùng phạm vi như thế nào?
Bạn thiết kế quy tắc phối hợp để một Colleague không vô tình kích hoạt chuỗi thông báo vòng lặp vô hạn như thế nào?
Bạn xử lý trường hợp Mediator nhận thông báo từ một Colleague chưa được đăng ký hoặc đã bị hủy như thế nào?
Bạn xác định thời điểm khởi tạo và gắn các Colleague vào Mediator để tránh đối tượng ở trạng thái chưa sẵn sàng ra sao?
Bạn quản lý việc bổ sung hoặc loại bỏ Colleague khi giao diện và các thành phần được tạo động như thế nào?
Bạn thiết kế ranh giới vòng đời Mediator để tránh giữ tham chiếu tới đối tượng không còn sử dụng ra sao?
Bạn bảo vệ bất biến của một nhóm Colleague khi một sự kiện đòi hỏi cập nhật đồng thời nhiều đối tượng như thế nào?
Bạn lựa chọn cập nhật đồng bộ hay gửi thông báo bất đồng bộ qua Mediator theo yêu cầu nhất quán của hệ thống như thế nào?
Khi nhiều luồng cùng gửi thông báo tới Mediator, bạn xác định những trạng thái chia sẻ nào cần được đồng bộ ra sao?
Bạn phân tích nguy cơ race condition nếu hai Colleague yêu cầu thay đổi cùng một trạng thái thông qua Mediator như thế nào?
Bạn xác định quy tắc thứ tự xử lý sự kiện khi kết quả cuối phụ thuộc vào thứ tự các thông báo tới Mediator ra sao?
Bạn xử lý ngoại lệ từ một Colleague trong lúc Mediator đang điều phối các thành phần khác như thế nào?
Bạn thiết kế chính sách tiếp tục hay dừng điều phối khi một bước phối hợp thất bại dựa trên những tiêu chí nào?
Bạn giải thích dấu hiệu Mediator đang biến thành một lớp quá lớn chứa quá nhiều quy tắc không liên quan như thế nào?
Bạn tách một Mediator phức tạp thành các nhóm phối hợp nhỏ mà không khôi phục phụ thuộc trực tiếp giữa Colleague như thế nào?
Bạn lựa chọn phạm vi Mediator theo một màn hình, một workflow hay toàn ứng dụng dựa trên mức độ gắn kết của các thành phần ra sao?
Bạn phân biệt logic điều phối với quy tắc nghiệp vụ cốt lõi để Mediator không trở thành nơi chứa toàn bộ logic của hệ thống như thế nào?
Bạn thiết kế logging để theo dõi Colleague nào gửi thông báo và Mediator quyết định hành động gì mà không làm rối giao diện ra sao?
Bạn giải quyết việc nhiều sự kiện lặp lại liên tục gây cập nhật thừa bằng cơ chế lọc hoặc gộp thông báo nào?
Bạn đánh giá ảnh hưởng của Mediator đối với thời gian phản hồi khi mọi tương tác đều đi qua một điểm điều phối như thế nào?
Bạn kiểm thử một Colleague độc lập bằng Mediator giả để xác nhận thông điệp được phát đúng trong những tình huống nào?
Bạn kiểm thử Mediator bằng các Colleague giả lập để kiểm chứng quy tắc chọn đối tượng nhận thông báo ra sao?
Bạn xây dựng test cho một chuỗi tương tác nhiều bước để xác nhận trạng thái cuối của các Colleague mà không khóa chặt từng lời gọi nội bộ như thế nào?
Bạn thiết kế test phát hiện vòng thông báo hoặc một Colleague bị gọi lặp khi có hai sự kiện đến gần như đồng thời ra sao?
Bạn phân biệt kiểm tra tương tác bằng mock với kiểm chứng trạng thái nghiệp vụ khi đánh giá một Mediator như thế nào?
Bạn tổ chức dependency injection cho Mediator và các Colleague để tránh tạo vòng tham chiếu khởi tạo ra sao?
Bạn xác định các điểm mở rộng của Mediator khi thêm một loại Colleague mới nhưng vẫn giữ được hành vi hiện có như thế nào?
Bạn phân tích tác động của việc thêm một quy tắc phối hợp mới đối với trách nhiệm và khả năng kiểm thử của Mediator ra sao?
Bạn cân nhắc dùng cấu hình khai báo hay mã điều kiện trong Mediator khi quy tắc phối hợp thường xuyên thay đổi như thế nào?
Bạn chuyển một thiết kế nhiều callback trực tiếp giữa các thành phần giao diện sang Mediator theo những bước ít rủi ro nào?
Bạn nhận diện những tương tác đơn giản không cần Mediator để tránh tạo lớp trung gian chỉ chuyển tiếp lời gọi như thế nào?
Bạn so sánh khả năng tái sử dụng của Colleague trước và sau khi tách các phụ thuộc ngang hàng vào Mediator ra sao?
Bạn xử lý yêu cầu tương thích khi các Colleague cũ vẫn dùng liên kết trực tiếp nhưng thành phần mới đã dùng Mediator như thế nào?
Bạn đánh giá chi phí điều phối tập trung so với lợi ích giảm coupling khi số Colleague và loại sự kiện tăng mạnh như thế nào?
Bạn lựa chọn những bằng chứng nào từ sơ đồ phụ thuộc, test và lịch sử thay đổi để quyết định có nên áp dụng Mediator cho một thiết kế cụ thể?
