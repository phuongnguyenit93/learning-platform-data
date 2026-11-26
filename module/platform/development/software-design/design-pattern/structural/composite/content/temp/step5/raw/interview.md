Bạn sẽ giải thích mục tiêu của mẫu Composite khi biểu diễn quan hệ phần–toàn thể thành cấu trúc cây như thế nào?
Bạn sẽ nhận diện tình huống dùng Composite khi client cần thao tác thống nhất với phần tử đơn và nhóm phần tử ra sao?
Bạn sẽ phân biệt vai trò Component, Leaf và Composite trong sơ đồ lớp UML như thế nào?
Bạn sẽ thiết kế Component interface để cả Leaf và Composite có thể thực hiện những thao tác chung như thế nào?
Bạn sẽ xác định những hành vi thực sự có ý nghĩa với cả Leaf và Composite để tránh một interface quá rộng ra sao?
Bạn sẽ mô tả cách Composite ủy quyền một thao tác cho các nút con mà không để client biết cấu trúc chi tiết như thế nào?
Bạn sẽ xây dựng ví dụ menu nhiều cấp bằng Composite và quyết định đâu là Leaf, đâu là Composite ra sao?
Bạn sẽ áp dụng Composite để tính tổng dung lượng của thư mục và các tệp con theo kiểu đệ quy như thế nào?
Bạn sẽ so sánh cách xử lý cây bằng Composite với việc client liên tục kiểm tra loại từng nút qua instanceof ra sao?
Bạn sẽ quyết định cung cấp add, remove và getChild trong Component hay chỉ trong Composite dựa trên đánh đổi nào?
Bạn sẽ phân biệt thiết kế Composite ưu tiên tính thống nhất của API với thiết kế ưu tiên an toàn kiểu như thế nào?
Bạn sẽ xác định hành vi khi client cố thêm nút con vào một Leaf mà API cho phép thao tác quản lý con ra sao?
Bạn sẽ bảo vệ danh sách con của Composite để code ngoài không sửa trực tiếp và phá vỡ các bất biến như thế nào?
Bạn sẽ quyết định có cho phép một nút xuất hiện trong nhiều nhánh khác nhau hay yêu cầu một nút chỉ có một cha như thế nào?
Bạn sẽ ngăn việc thêm một Composite làm con của chính nó hoặc một hậu duệ của nó tạo thành chu trình ra sao?
Bạn sẽ thiết kế cơ chế lưu tham chiếu đến nút cha khi cần truy vết vị trí mà vẫn tránh phụ thuộc vòng không cần thiết như thế nào?
Bạn sẽ giữ nhất quán quan hệ cha–con khi di chuyển một nút từ nhánh này sang nhánh khác như thế nào?
Bạn sẽ xác định chính sách khi thêm hai nút có cùng định danh hoặc cùng tên vào một Composite ra sao?
Bạn sẽ quyết định thứ tự các nút con có phải là một phần của hợp đồng hay không trong ứng dụng menu như thế nào?
Bạn sẽ kiểm soát sự khác nhau giữa một Composite rỗng và một Leaf có kết quả thao tác tương tự ra sao?
Bạn sẽ triển khai phép đếm toàn bộ nút hoặc nút lá trong cây mà không làm sai kết quả khi cây thay đổi như thế nào?
Bạn sẽ thiết kế tính toán tổng hợp trên cây khi một Leaf trả lỗi hoặc không có dữ liệu hợp lệ ra sao?
Bạn sẽ lựa chọn duyệt tiền tự, hậu tự hoặc theo mức tùy theo mục tiêu xử lý cây như thế nào?
Bạn sẽ đánh giá khi nào cần dùng thuật toán duyệt lặp với stack thay cho đệ quy để tránh tràn ngăn xếp như thế nào?
Bạn sẽ thiết kế Iterator cho Composite để client duyệt phần tử mà không truy cập trực tiếp cấu trúc lưu trữ như thế nào?
Bạn sẽ kiểm tra tính nhất quán của kết quả khi một nút bị xóa hoặc thêm trong lúc đang duyệt cây ra sao?
Bạn sẽ phân tích rủi ro nhiều luồng đồng thời đọc và thay đổi một cấu trúc Composite dùng chung như thế nào?
Bạn sẽ lựa chọn cấu trúc Composite bất biến hay có thể sửa đổi dựa trên tần suất thay đổi và nhu cầu chia sẻ như thế nào?
Bạn sẽ xác định cách đồng bộ việc chỉnh sửa cây để không tạo trạng thái chỉ cập nhật một nửa quan hệ cha–con như thế nào?
Bạn sẽ cân nhắc lưu kết quả tính tổng ở mỗi Composite để tăng tốc và cách vô hiệu hóa cache khi con thay đổi ra sao?
Bạn sẽ đánh giá chi phí bộ nhớ của các nút trung gian và tham chiếu con khi cây có số lượng phần tử rất lớn như thế nào?
Bạn sẽ xác định khi nào cần tải nút con theo nhu cầu thay vì dựng toàn bộ cây trong bộ nhớ ra sao?
Bạn sẽ tổ chức hiển thị cây giao diện có thể mở rộng và thu gọn mà vẫn tách cấu trúc dữ liệu khỏi chi tiết render như thế nào?
Bạn sẽ thiết kế cơ chế bật hoặc tắt một nhánh menu và xác định tác động của nó tới các phần tử con như thế nào?
Bạn sẽ phân biệt logic biểu diễn cây với logic quyền truy cập khi các nút menu có thể bị ẩn theo người dùng ra sao?
Bạn sẽ kiểm soát việc tổng hợp kết quả từ một nhánh không được phép truy cập để tránh lộ dữ liệu như thế nào?
Bạn sẽ thiết kế thao tác tìm kiếm theo điều kiện trong cây và trả về đường dẫn tới nút phù hợp ra sao?
Bạn sẽ xử lý một thao tác xóa Composite mà các nút con đang được thành phần khác tham chiếu như thế nào?
Bạn sẽ lựa chọn chính sách sao chép một nhánh cây khi cần tái sử dụng cấu trúc nhưng không muốn chia sẻ trạng thái như thế nào?
Bạn sẽ phân biệt sao chép nông và sao chép sâu đối với Composite có nhiều mức nút con ra sao?
Bạn sẽ thiết kế cách tuần tự hóa và khôi phục cây mà vẫn giữ đúng định danh, thứ tự và quan hệ cha–con như thế nào?
Bạn sẽ nhận diện dấu hiệu cần một mô hình đồ thị thay vì Composite khi một nút có nhiều cha hoặc các liên kết tạo chu trình ra sao?
Bạn sẽ so sánh Composite với Decorator khi cả hai dùng quan hệ bao chứa đối tượng nhưng có mục tiêu khác nhau như thế nào?
Bạn sẽ giải thích cách kết hợp Composite với Visitor khi cần bổ sung nhiều phép xử lý trên cùng cấu trúc cây ra sao?
Bạn sẽ kiểm thử Leaf độc lập để xác minh hành vi của nó phù hợp với hợp đồng Component như thế nào?
Bạn sẽ thiết kế unit test cho Composite rỗng, một nút con và nhiều cấp lồng nhau ra sao?
Bạn sẽ kiểm thử các bất biến khi thêm, xóa, di chuyển nút và thử cố ý tạo chu trình như thế nào?
Bạn sẽ xây dựng phép kiểm thử so sánh kết quả tổng hợp giữa cây sâu và cây rộng để phát hiện lỗi duyệt như thế nào?
Bạn sẽ refactor mã Java đang xử lý riêng thư mục và tệp bằng điều kiện loại thành Composite từng bước ra sao?
Bạn sẽ đánh giá Composite có thật sự giảm nhánh điều kiện, tăng khả năng mở rộng và giữ API dễ hiểu như thế nào?
