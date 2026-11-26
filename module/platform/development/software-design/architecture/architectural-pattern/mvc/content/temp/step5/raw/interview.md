Bạn sẽ giải thích mục tiêu của mô hình Model–View–Controller trong việc phân tách trạng thái, trình bày và tương tác như thế nào?
Bạn sẽ xác định trách nhiệm của Model, View và Controller qua chức năng tra cứu đơn hàng ra sao?
Bạn sẽ mô tả luồng request từ trình duyệt đến Controller, Model, View rồi trả response như thế nào?
Bạn sẽ phân biệt Model trong MVC với một bảng dữ liệu hoặc entity lưu trữ trong cơ sở dữ liệu ra sao?
Bạn sẽ tổ chức các quy tắc nghiệp vụ để Controller không trở thành nơi chứa toàn bộ xử lý của ứng dụng như thế nào?
Bạn sẽ phân biệt trách nhiệm của Controller và application service khi cần cập nhật nhiều đối tượng nghiệp vụ ra sao?
Bạn sẽ thiết kế giao diện giữa Controller và tầng nghiệp vụ để có thể kiểm thử độc lập như thế nào?
Bạn sẽ lựa chọn dữ liệu nào cần đưa vào Model của một trang web mà không làm lộ dữ liệu nội bộ ra sao?
Bạn sẽ kiểm soát việc View chỉ trình bày dữ liệu thay vì thực hiện truy vấn hoặc thay đổi nghiệp vụ như thế nào?
Bạn sẽ phân biệt MVC dùng template server-side với ứng dụng cung cấp JSON API cho frontend độc lập ra sao?
Bạn sẽ phân tích vai trò của routing và HTTP method khi Controller tiếp nhận các thao tác của người dùng như thế nào?
Bạn sẽ tổ chức đường dẫn và tên hành động của Controller để phản ánh tài nguyên hoặc mục đích rõ ràng ra sao?
Bạn sẽ thiết kế hợp đồng request và response nhất quán giữa nhiều Controller trong cùng ứng dụng như thế nào?
Bạn sẽ chọn DTO riêng cho dữ liệu nhập và dữ liệu hiển thị thay vì truyền trực tiếp domain entity như thế nào?
Bạn sẽ xác định trường bắt buộc, giá trị mặc định và lỗi kiểu dữ liệu khi binding một biểu mẫu vào đối tượng Java ra sao?
Bạn sẽ phân biệt validation về cú pháp đầu vào với validation về quy tắc nghiệp vụ trong luồng xử lý biểu mẫu như thế nào?
Bạn sẽ trả lại thông báo lỗi và giữ dữ liệu người dùng đã nhập trên biểu mẫu khi validation thất bại ra sao?
Bạn sẽ thiết kế thông báo lỗi theo từng trường và lỗi toàn biểu mẫu để người dùng sửa chính xác như thế nào?
Bạn sẽ ngăn người dùng gửi thêm các trường không được phép chỉnh sửa khi binding form vào đối tượng như thế nào?
Bạn sẽ kiểm chứng các tham số path, query và dữ liệu body được Controller diễn giải đúng theo hợp đồng như thế nào?
Bạn sẽ phân biệt xử lý GET để đọc dữ liệu với POST để thay đổi trạng thái và tác động đến trải nghiệm người dùng ra sao?
Bạn sẽ sử dụng mô hình Post/Redirect/Get để tránh gửi lại biểu mẫu khi người dùng tải lại trang như thế nào?
Bạn sẽ quyết định dữ liệu nào nên đi qua redirect attribute, session hay URL khi chuyển giữa các request ra sao?
Bạn sẽ kiểm soát trạng thái hội thoại người dùng trong MVC mà không tạo phụ thuộc vào một máy chủ cụ thể như thế nào?
Bạn sẽ thiết kế View để hiển thị danh sách rỗng, dữ liệu thiếu hoặc lỗi tải dữ liệu mà vẫn có trải nghiệm rõ ràng ra sao?
Bạn sẽ lựa chọn cấu trúc template, component và layout dùng chung để tránh lặp trình bày giữa nhiều trang như thế nào?
Bạn sẽ bảo đảm các giá trị do người dùng nhập được escape đúng ngữ cảnh khi render HTML để phòng tránh XSS ra sao?
Bạn sẽ phân biệt escaping dữ liệu khi xuất vào nội dung HTML, thuộc tính HTML và JavaScript như thế nào?
Bạn sẽ thiết kế cơ chế chống CSRF cho thao tác thay đổi trạng thái khi ứng dụng xác thực bằng cookie như thế nào?
Bạn sẽ xác định bước nào của luồng request cần xác thực danh tính và kiểm tra quyền truy cập tài nguyên ra sao?
Bạn sẽ xử lý trường hợp người dùng thay ID trong URL để truy cập một đơn hàng không thuộc quyền của họ như thế nào?
Bạn sẽ quyết định trả trang đăng nhập, trang từ chối truy cập hoặc trang không tìm thấy theo ngữ cảnh bảo mật ra sao?
Bạn sẽ kiểm soát việc Controller xử lý ngoại lệ nghiệp vụ thành status và thông báo phù hợp như thế nào?
Bạn sẽ thiết kế bộ xử lý lỗi dùng chung mà vẫn giữ đủ ngữ cảnh để điều tra sự cố trong log ra sao?
Bạn sẽ phân biệt lỗi validation, lỗi tài nguyên không tồn tại và lỗi hệ thống khi xây dựng trang lỗi hoặc phản hồi API như thế nào?
Bạn sẽ tránh để stack trace, thông tin kết nối hoặc dữ liệu nhạy cảm xuất hiện trong View hay response lỗi ra sao?
Bạn sẽ lựa chọn cách thực hiện phân trang, sắp xếp và lọc để View không cần biết chi tiết truy vấn dữ liệu như thế nào?
Bạn sẽ xử lý việc tải dữ liệu liên quan trước khi render View để tránh truy vấn phát sinh bất ngờ trong template ra sao?
Bạn sẽ xác định ranh giới transaction khi Controller gọi service rồi hiển thị kết quả như thế nào?
Bạn sẽ kiểm tra các yêu cầu tải tệp lên qua Controller về dung lượng, loại tệp và quyền truy cập như thế nào?
Bạn sẽ thiết kế phản hồi tải tệp xuống gồm tên, kiểu nội dung và chính sách cache phù hợp ra sao?
Bạn sẽ dùng unit test để xác minh Controller gọi đúng use case mà không phải khởi động toàn bộ ứng dụng như thế nào?
Bạn sẽ kiểm thử binding và validation của biểu mẫu bằng các trường hợp thiếu, sai kiểu và giá trị biên ra sao?
Bạn sẽ sử dụng MockMvc để xác minh route, status, Model và tên View trong một ứng dụng Spring MVC như thế nào?
Bạn sẽ xây dựng integration test cho luồng gửi biểu mẫu, redirect và hiển thị thông báo thành công ra sao?
Bạn sẽ kiểm chứng quyền truy cập, CSRF và xử lý lỗi của các endpoint MVC ở những lớp kiểm thử nào?
Bạn sẽ phát hiện tình huống View render đúng nhưng Controller gọi nhầm nghiệp vụ hoặc bỏ qua validation bằng cách nào?
Bạn sẽ cân nhắc khi nào MVC phù hợp với ứng dụng web và khi nào cần tổ chức thêm các tầng nghiệp vụ, persistence riêng ra sao?
Bạn sẽ chuyển một ứng dụng có logic xen lẫn trong template và Controller sang MVC rõ ràng mà vẫn giữ hành vi như thế nào?
Bạn sẽ xử lý tình huống một thay đổi biểu mẫu khiến cả dữ liệu lưu trữ lẫn trang hiển thị bị sai mà các test Controller vẫn thành công ra sao?
