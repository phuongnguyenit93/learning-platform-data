Bạn sẽ giải thích mục tiêu của các nguyên tắc thiết kế phần mềm bằng những thay đổi thực tế nào trong chi phí hiểu và sửa mã?
Khi nhận một yêu cầu mới, bạn sẽ xác định các trách nhiệm độc lập trước khi quyết định chia lớp và module như thế nào?
Bạn sẽ phân biệt trách nhiệm nghiệp vụ với trách nhiệm trình bày, lưu trữ và tích hợp bên ngoài bằng tiêu chí nào?
Bạn sẽ áp dụng separation of concerns để ngăn logic tính giá nằm lẫn trong controller và repository ra sao?
Khi cùng một quy tắc xuất hiện ở nhiều nơi, bạn sẽ quyết định nên tập trung nó hay chấp nhận sự lặp lại có chủ đích như thế nào?
Bạn sẽ phân biệt đóng gói dữ liệu với đóng gói bất biến và hành vi của đối tượng như thế nào?
Bạn sẽ thiết kế API để caller không thể đặt một đối tượng vào trạng thái nghiệp vụ không hợp lệ ra sao?
Khi một lớp cung cấp quá nhiều setter, bạn sẽ nhận ra những nguy cơ và điều chỉnh giao diện công khai như thế nào?
Bạn sẽ lựa chọn mức abstraction vừa đủ để che giấu chi tiết thay đổi mà không tạo interface hình thức ra sao?
Bạn sẽ phân biệt một abstraction dựa trên nhu cầu client với một abstraction phản chiếu toàn bộ lớp triển khai như thế nào?
Bạn sẽ đánh giá độ cohesion của một lớp dựa trên mối liên hệ giữa dữ liệu, hành vi và lý do thay đổi như thế nào?
Khi một class vừa xử lý xác thực vừa xuất báo cáo, bạn sẽ phân tách trách nhiệm và kiểm tra tính nhất quán của kết quả ra sao?
Bạn sẽ phát hiện coupling cao từ việc một thay đổi nhỏ gây sửa hàng loạt lớp ở nhiều tầng bằng cách nào?
Bạn sẽ lựa chọn điểm đặt ranh giới module dựa trên các nhóm thay đổi thường xảy ra cùng nhau như thế nào?
Bạn sẽ giải thích sự khác biệt giữa coupling ở thời điểm biên dịch và sự phụ thuộc vận hành khi các thành phần tương tác ra sao?
Bạn sẽ dùng SRP để đánh giá một lớp có nhiều phương thức nhưng vẫn có thể chỉ có một trách nhiệm như thế nào?
Khi áp dụng Open/Closed Principle, bạn sẽ xác định phần nào cần mở rộng và phần nào thực sự cần giữ ổn định ra sao?
Bạn sẽ tránh việc tạo quá nhiều lớp trừu tượng chỉ để tuân thủ Open/Closed Principle như thế nào?
Bạn sẽ nhận biết lớp con vi phạm Liskov Substitution khi tăng tiền điều kiện hoặc làm yếu hậu điều kiện ra sao?
Bạn sẽ thiết kế phép kiểm thử nào để xác nhận các implementation thay thế nhau đúng theo hợp đồng chung?
Khi một interface buộc client phụ thuộc vào các phương thức không dùng, bạn sẽ phân tích vi phạm Interface Segregation như thế nào?
Bạn sẽ chia một interface lớn thành các hợp đồng theo nhu cầu caller mà vẫn giữ được khả năng phối hợp ra sao?
Bạn sẽ áp dụng Dependency Inversion để chính sách nghiệp vụ không import trực tiếp thư viện lưu trữ như thế nào?
Bạn sẽ xác định nơi đặt interface trong kiến trúc để hướng phụ thuộc trỏ về chính sách thay vì công nghệ ra sao?
Bạn sẽ phân biệt Dependency Inversion Principle với cơ chế dependency injection trong một thiết kế cụ thể như thế nào?
Bạn sẽ lựa chọn constructor injection hay phương thức injection dựa trên tính bắt buộc và vòng đời dependency như thế nào?
Bạn sẽ giải thích vì sao tự tạo dependency bằng new trong logic nghiệp vụ có thể làm test khó thay thế cộng tác viên ra sao?
Khi một lớp chỉ chuyển tiếp nhiều lời gọi, bạn sẽ xác định đó là ranh giới có ý nghĩa hay lớp trung gian dư thừa như thế nào?
Bạn sẽ dùng composition để phối hợp các hành vi thay vì xây dựng hệ phân cấp kế thừa theo những điều kiện nào?
Bạn sẽ chỉ ra tình huống kế thừa vẫn phù hợp và cách bảo đảm hợp đồng lớp cha không bị vi phạm ra sao?
Khi một đối tượng vừa tính toán vừa quản lý I/O, bạn sẽ tách phần thuần túy ra để kiểm thử nhanh hơn như thế nào?
Bạn sẽ so sánh kiểm thử trạng thái và kiểm thử tương tác khi đánh giá độ đúng của một thiết kế có nhiều dependency ra sao?
Bạn sẽ xác định khi nào dùng mock để cô lập một boundary và khi nào dùng thành phần thật trong kiểm thử tích hợp như thế nào?
Bạn sẽ thiết kế thông báo lỗi và giá trị trả về qua ranh giới module để không rò rỉ chi tiết nội bộ ra sao?
Khi một API công khai thay đổi, bạn sẽ đánh giá blast radius và kế hoạch giữ tương thích theo những tín hiệu nào?
Bạn sẽ nhận biết một lớp God Object qua trách nhiệm, mức độ phụ thuộc và lịch sử sửa đổi bằng cách nào?
Bạn sẽ phân tích hiện tượng feature envy và cách di chuyển hành vi về nơi sở hữu dữ liệu phù hợp ra sao?
Bạn sẽ quyết định lúc nào nên dùng Extract Class hoặc Extract Method để cải thiện tính dễ hiểu mà không chia nhỏ quá mức như thế nào?
Khi hai module cần sử dụng dữ liệu chung, bạn sẽ tránh biến chia sẻ trạng thái thành phụ thuộc ngầm như thế nào?
Bạn sẽ đánh giá tác động của cấu trúc package theo tầng kỹ thuật so với theo chức năng nghiệp vụ đến khả năng thay đổi ra sao?
Bạn sẽ phân biệt nguyên tắc thiết kế với quy tắc tuyệt đối khi yêu cầu hiệu năng xung đột với khả năng mở rộng như thế nào?
Khi thêm abstraction làm tăng số lượng lớp, bạn sẽ đo lợi ích bảo trì dự kiến để quyết định giữ hay bỏ ra sao?
Bạn sẽ dùng độ phức tạp của API, số dependency và thời gian hiểu mã để đánh giá chất lượng thiết kế như thế nào?
Bạn sẽ quyết định chấp nhận một mức coupling có chủ đích giữa hai thành phần có vòng đời thay đổi giống nhau ra sao?
Khi refactor mã cũ theo SOLID, bạn sẽ lựa chọn một thay đổi nhỏ có thể kiểm chứng trước khi đổi toàn bộ kiến trúc như thế nào?
Bạn sẽ xây dựng kiểm thử hồi quy để chứng minh hành vi không thay đổi sau khi tách trách nhiệm như thế nào?
Bạn sẽ tổ chức review thiết kế để thảo luận bằng ví dụ thay đổi dự kiến thay vì chỉ dùng tên nguyên tắc như thế nào?
Khi hai nguyên tắc gợi ý hướng thiết kế khác nhau, bạn sẽ đánh giá các trade-off và ưu tiên ra sao?
Bạn sẽ nhận biết dấu hiệu một thiết kế bị overengineering dù bề ngoài có nhiều interface và pattern như thế nào?
Bạn sẽ lựa chọn các chỉ số hoặc bằng chứng nào để kiểm chứng thiết kế mới thực sự giảm chi phí tiến hóa phần mềm?
