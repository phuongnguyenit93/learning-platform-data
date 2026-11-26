Khi nhiều đối tượng giao diện gọi chéo nhau, Mediator giúp điều gì?
A. Gom quy tắc phối hợp vào mediator chung
B. Để từng nút giữ tham chiếu đến mọi nút còn lại
C. Đưa mọi trạng thái giao diện vào biến toàn cục
D. Cho từng nút gọi trực tiếp cơ sở dữ liệu
Đáp án đúng: A

Trong mẫu Mediator, colleague thường giao tiếp với thành phần khác ra sao?
A. Gọi qua chuỗi kế thừa giữa các colleague
B. Gửi request thẳng tới từng đồng nghiệp liên quan
C. Báo mediator để điều phối liên lạc
D. Tự tìm mọi colleague trong danh sách toàn cục
Đáp án đúng: C

Mẫu Mediator phù hợp nhất với tình huống nào dưới đây?
A. Một đối tượng chỉ cần phát sự kiện cho listener
B. Các control có nhiều ràng buộc tương tác
C. Một hàm thuần chỉ cộng hai giá trị số nguyên
D. Một cấu trúc dữ liệu cần sao chép trạng thái cũ
Đáp án đúng: B

Khi ô chọn phương thức giao hàng đổi giá trị, cách phối hợp nào phù hợp Mediator?
A. Ô chọn tự truy cập trạng thái mọi control trên màn
B. Báo mediator để cập nhật control liên quan
C. Từng control tự kiểm tra thay đổi bằng vòng lặp
D. Controller bỏ qua thay đổi cho đến lần lưu dữ liệu
Đáp án đúng: B

Vai trò của concrete mediator trong một hệ thống đơn giản là gì?
A. Thay thế toàn bộ logic nội tại của các colleague
B. Lưu trữ bản sao bất biến của mọi colleague
C. Chỉ định mọi colleague phải kế thừa cùng một lớp
D. Quy định cách các colleague phối hợp hoạt động
Đáp án đúng: D

Khi thêm một colleague mới, lợi ích nào có thể đạt được?
A. Mediator tự suy ra toàn bộ chức năng mới từ tên lớp
B. Mọi colleague luôn giữ cùng một trạng thái nội tại
C. Giảm nhu cầu sửa liên kết trực tiếp giữa colleague
D. Không cần thay đổi bất kỳ luật phối hợp hiện có
Đáp án đúng: C

Mối quan hệ giữa Observer và Mediator được hiểu đúng ra sao?
A. Observer báo thay đổi; Mediator điều phối tương tác
B. Observer luôn yêu cầu một mediator để đăng ký listener
C. Mediator chỉ lưu lịch sử các thông báo đã phát
D. Hai mẫu đều buộc mọi đối tượng giao tiếp trực tiếp
Đáp án đúng: A

Nếu mediator chứa quá nhiều quy tắc không liên quan, rủi ro nào xuất hiện?
A. Mọi quan hệ phụ thuộc giữa lớp đều biến mất
B. Mỗi phương thức mediator sẽ mặc định chạy song song
C. Các colleague sẽ tự động giảm số lượng trạng thái
D. Nó có thể thành lớp lớn khó duy trì và kiểm thử
Đáp án đúng: D

Muốn thay cách điều phối mà không sửa colleague, thiết kế nào hữu ích?
A. Để colleague chỉnh source mediator ở thời gian chạy
B. Cho colleague phụ thuộc interface mediator ổn định
C. Để colleague khởi tạo trực tiếp mọi mediator cụ thể
D. Đưa mã gọi colleague khác vào từng callback riêng
Đáp án đúng: B

Một unit test cho mediator của biểu mẫu nên xác minh điều gì?
A. Chỉ số lượng file Java trong phần presentation
B. Tốc độ khởi động IDE khi mở dự án giao diện
C. Cách JVM phân bổ bộ nhớ cho mọi lớp UI
D. Kiểm tra control đổi đúng theo sự kiện nhận được
Đáp án đúng: D

Vì sao event gọi lồng nhau trong mediator cần được thiết kế cẩn thận?
A. Mọi callback chỉ có thể được gọi đúng một lần
B. Callback có thể gây vòng gọi lặp liên tục
C. Từng colleague tự chặn mọi lệnh gọi phát sinh
D. Mediator luôn tự loại bỏ mọi sự kiện bị gửi lặp
Đáp án đúng: B

Khi giao tiếp qua mediator, cách nào giúp giới hạn coupling?
A. Trao đổi qua sự kiện hoặc API với hợp đồng rõ ràng
B. Buộc colleague phụ thuộc tất cả lớp triển khai cụ thể
C. Truyền toàn bộ tham chiếu đối tượng của hệ thống
D. Để mọi colleague đọc trực tiếp dữ liệu private khác
Đáp án đúng: A

Trong ví dụ phòng chat, vai trò mediator phù hợp là gì?
A. Lưu tất cả thông tin đăng nhập của hệ điều hành
B. Thay thế hoàn toàn giao thức truyền tin tầng mạng
C. Chuyển tin giữa người tham gia theo quy tắc phòng
D. Buộc người gửi biết từng người nhận qua tham chiếu
Đáp án đúng: C

Khi nào có thể chưa cần đưa Mediator vào thiết kế?
A. Luồng phối hợp thay đổi thường xuyên giữa các control
B. Cần cô lập giao tiếp giữa nhiều thành phần giao diện
C. Các đối tượng ít tương tác và liên kết còn đơn giản
D. Có nhiều component với điều kiện phụ thuộc chéo nhau
Đáp án đúng: C

Khi chuyển từ gọi chéo sang Mediator, bước refactor nào hợp lý?
A. Giữ nguyên toàn bộ lời gọi chéo và thêm mediator rỗng
B. Đưa mọi dữ liệu nghiệp vụ vào một singleton toàn cục
C. Đổi tất cả colleague thành các lớp abstract không hành vi
D. Dời quy tắc phối hợp khỏi colleague vào mediator
Đáp án đúng: D

Trong Mediator, quyền quyết định phản ứng trước một thông báo nên nằm ở đâu?
A. Trong logic điều phối của mediator theo hợp đồng
B. Trong mọi colleague theo bản sao quy tắc giống nhau
C. Trong cơ chế tự động của trình biên dịch Java
D. Trong đối tượng gửi bằng cách sửa trực tiếp bên nhận
Đáp án đúng: A
