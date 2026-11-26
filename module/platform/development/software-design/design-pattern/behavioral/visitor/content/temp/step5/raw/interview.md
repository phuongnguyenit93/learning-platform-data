Bạn sẽ mô tả vấn đề thiết kế nào được Visitor giải quyết khi có nhiều thao tác trên một cấu trúc đối tượng nhiều loại?
Bạn sẽ phân biệt trường hợp thêm hành vi mới thường xuyên với trường hợp thêm loại phần tử mới thường xuyên để quyết định dùng Visitor như thế nào?
Bạn sẽ giải thích vai trò của Element, Concrete Element, Visitor và Concrete Visitor trong một thiết kế điển hình ra sao?
Bạn sẽ thiết kế phương thức accept trên mỗi phần tử để chuyển quyền xử lý sang Visitor như thế nào?
Bạn sẽ giải thích double dispatch trong Visitor và sự khác biệt so với một lần gọi phương thức đa hình thông thường ra sao?
Khi Visitor có phương thức visit cho từng loại phần tử, bạn sẽ xác định phương thức nào được gọi trong một tình huống cụ thể như thế nào?
Bạn sẽ phân tích vì sao chỉ overload phương thức visit mà không có accept có thể chưa đủ để chọn đúng xử lý trong Java ra sao?
Trong mô hình cây biểu thức số học, bạn sẽ áp dụng Visitor để bổ sung thao tác tính giá trị mà không sửa từng lớp nút như thế nào?
Bạn sẽ thiết kế thêm một Visitor xuất biểu thức thành chuỗi mà vẫn giữ nguyên mô hình nút hiện có ra sao?
Khi duyệt một cây tài liệu, bạn sẽ quyết định đối tượng nào chịu trách nhiệm đi qua các phần tử con như thế nào?
Bạn sẽ phân biệt Visitor chỉ xử lý một nút với Visitor thực hiện luôn traversal qua cả cấu trúc như thế nào?
Bạn sẽ xử lý thứ tự duyệt trước, giữa hoặc sau các nút khi kết quả phụ thuộc vào cấu trúc cây ra sao?
Bạn sẽ thiết kế cách Visitor truyền ngữ cảnh từ nút cha xuống nút con mà không dùng trạng thái toàn cục như thế nào?
Khi một Visitor cần tổng hợp kết quả từ nhiều phần tử, bạn sẽ lựa chọn trạng thái trong Visitor hay giá trị trả về từ visit ra sao?
Bạn sẽ cân nhắc một Visitor có kết quả trả về theo kiểu generic khi các thao tác có kiểu kết quả khác nhau như thế nào?
Bạn sẽ tổ chức cách truyền tham số đầu vào cho từng lượt visit để tránh nhồi quá nhiều thuộc tính tạm vào đối tượng Visitor ra sao?
Khi cấu trúc chứa nút null hoặc phần tử tùy chọn, bạn sẽ định nghĩa hành vi xử lý vắng mặt trong hợp đồng như thế nào?
Bạn sẽ xử lý một loại phần tử chưa được Visitor hỗ trợ mà không âm thầm bỏ qua hành vi bắt buộc ra sao?
Khi thêm một lớp Concrete Element mới, bạn sẽ đánh giá những thay đổi bắt buộc trên interface Visitor và các lớp triển khai như thế nào?
Bạn sẽ phân tích vì sao việc thêm một thao tác mới bằng Concrete Visitor có thể thuận lợi hơn thêm phương thức vào mọi Element?
Bạn sẽ cân nhắc chi phí sửa nhiều Visitor khi hệ phân cấp phần tử thay đổi liên tục và kết luận mức phù hợp của mẫu ra sao?
Bạn sẽ bảo vệ tính đóng gói của Element khi Visitor cần đọc dữ liệu nhưng không được quyền thay đổi trạng thái nội bộ như thế nào?
Khi một Visitor cần cập nhật phần tử, bạn sẽ kiểm soát bất biến của mô hình thay vì cho phép sửa trường trực tiếp ra sao?
Bạn sẽ phân biệt Visitor chỉ đọc với Visitor có tác dụng phụ trong thiết kế API và cách kiểm thử như thế nào?
Bạn sẽ thiết kế cơ chế báo lỗi khi xử lý một phần tử thất bại để caller biết vị trí xảy ra sự cố ra sao?
Khi duyệt một cây rất sâu, bạn sẽ xem xét nguy cơ tràn stack từ đệ quy và cách thay đổi thuật toán duyệt như thế nào?
Bạn sẽ xác định cách phát hiện chu trình nếu cấu trúc là đồ thị chứ không phải cây để tránh Visitor lặp vô hạn ra sao?
Khi cùng một nút được chia sẻ giữa nhiều nhánh, bạn sẽ xác định có cần thăm lại nút hay ghi nhớ kết quả như thế nào?
Bạn sẽ kiểm soát việc tái sử dụng một Visitor có trạng thái giữa các lần duyệt để tránh trộn kết quả cũ và mới ra sao?
Khi nhiều luồng dùng chung một Visitor, bạn sẽ đánh giá an toàn luồng và khả năng chia sẻ trạng thái theo tiêu chí nào?
Bạn sẽ áp dụng Visitor cho thao tác kiểm tra hợp lệ trên các loại thành phần tài liệu mà không chứa logic kiểm tra trong mỗi lớp như thế nào?
Bạn sẽ tách một Visitor kiểm tra điều kiện nghiệp vụ khỏi Visitor sinh báo cáo để mỗi thao tác có trách nhiệm rõ ra sao?
Bạn sẽ xác định khi nào một Visitor trở nên quá lớn vì chứa nhiều quy tắc không liên quan và cách chia nhỏ nó như thế nào?
Bạn sẽ thiết kế một adapter Visitor cho phần tử của thư viện không thể sửa để bổ sung phương thức accept bằng cách nào?
Bạn sẽ so sánh Visitor với việc dùng instanceof liên tiếp khi số loại phần tử được biết trước và ít thay đổi như thế nào?
Bạn sẽ đánh giá một giải pháp dựa trên pattern matching hoặc sealed hierarchy so với Visitor trong Java hiện đại bằng những tiêu chí nào?
Bạn sẽ phân biệt Visitor với Strategy khi cả hai đều tách hành vi khỏi đối tượng đang xử lý theo cách nào?
Bạn sẽ so sánh Visitor và Command khi mục tiêu là biểu diễn thao tác trên nhiều đối tượng theo những khía cạnh nào?
Bạn sẽ phân tích tác động của việc Visitor phụ thuộc vào các lớp Concrete Element đối với hướng phụ thuộc và khả năng đóng gói ra sao?
Bạn sẽ đặt tên các phương thức visit và kiểu phần tử thế nào để người dùng API không nhầm các overload?
Bạn sẽ viết test để chứng minh accept trên từng Concrete Element chuyển đúng loại đối tượng đến phương thức visit tương ứng như thế nào?
Bạn sẽ thiết kế bộ test cho Visitor tính tổng trên cây có nút lồng nhau, nút rỗng và nút có giá trị biên ra sao?
Bạn sẽ kiểm thử Visitor có tác dụng phụ sao cho mỗi phần tử được xử lý đúng số lần kỳ vọng như thế nào?
Bạn sẽ kiểm tra rằng việc thêm một Concrete Visitor không vô tình làm thay đổi trạng thái của cấu trúc phần tử như thế nào?
Bạn sẽ tổ chức dữ liệu thử nghiệm để phân biệt lỗi traversal với lỗi xử lý tại từng phương thức visit ra sao?
Bạn sẽ ước lượng chi phí cấp phát và lời gọi đa hình của Visitor trên một cấu trúc lớn mà không suy luận hiệu năng chỉ từ lý thuyết như thế nào?
Khi refactor một đoạn mã xử lý từng loại nút bằng switch, bạn sẽ chuyển sang Visitor từng bước và giữ kết quả cũ ra sao?
Bạn sẽ xác định những trường hợp không nên dùng Visitor vì các phần tử hiếm khi giữ cấu trúc ổn định như thế nào?
Bạn sẽ xây dựng quy ước kiểm soát thay đổi để một loại phần tử mới không làm thiếu triển khai ở các Visitor hiện có ra sao?
Bạn sẽ đánh giá hiệu quả thiết kế sau khi dùng Visitor bằng khả năng thêm thao tác mới, độ rõ của kiểu dữ liệu và chi phí bảo trì như thế nào?
