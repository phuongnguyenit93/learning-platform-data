Một đơn hàng đổi cách xử lý theo trạng thái hiện tại; mẫu nào phù hợp?
A. State đóng gói hành vi ứng với từng trạng thái
B. Strategy chọn thuật toán theo cấu hình cố định
C. Observer gửi thông báo đến các listener đăng ký
D. Memento khôi phục snapshot của lần chạy trước
Đáp án đúng: A

Trong State Pattern, Context thường thực hiện nhiệm vụ nào?
A. Tự lưu bản sao lịch sử mỗi thao tác trước đó
B. Chọn tất cả thuật toán qua một biến toàn cục
C. Giữ danh sách subscriber để phát tất cả event
D. Giữ State hiện tại và ủy quyền hành vi cho nó
Đáp án đúng: D

Các Concrete State nên chịu trách nhiệm chính nào?
A. Chứa toàn bộ code giao diện và điều hướng UI
B. Thực hiện mọi thao tác JDBC của toàn hệ thống
C. Chỉ chuyển đổi giữa các loại DTO đầu vào
D. Hiện thực cách xử lý phù hợp với từng state
Đáp án đúng: D

Trong State Pattern, việc chuyển trạng thái có thể được tổ chức thế nào?
A. Từng service đọc trực tiếp trường private của State
B. Context luôn bị cấm cập nhật State sau khởi tạo
C. State yêu cầu Context đổi state theo quy tắc
D. Trình biên dịch Java tự sinh mọi cạnh chuyển
Đáp án đúng: C

Đơn hàng đã giao không còn được hủy; thiết kế nào phù hợp?
A. State ĐãGiao chuyển thẳng về trạng thái Mới
B. State ĐãGiao bác bỏ yêu cầu hủy theo luật
C. Bất kỳ State nào cũng cho phép mọi thao tác
D. Context cho hủy vì người dùng gửi HTTP 200
Đáp án đúng: B

Trước khi chuyển từ ChờThanhToán sang ĐãTrả, nên làm gì?
A. Kiểm tra điều kiện và bất biến của transition
B. Chỉ ghi tên lớp State vào log rồi kết thúc
C. Cập nhật State trước rồi bỏ qua xác nhận thanh toán
D. Tự đổi mọi State đang tồn tại sang ĐãTrả
Đáp án đúng: A

Một lệnh không hợp lệ với State hiện tại nên có cách xử lý nào?
A. Chuyển ngẫu nhiên sang State gần nhất trong danh sách
B. Báo lỗi rõ hoặc từ chối mà không phá trạng thái
C. Lặp lệnh vô hạn đến khi State khác chấp nhận
D. Bỏ các điều kiện kiểm tra để tăng tốc xử lý
Đáp án đúng: B

Khi Concrete State không chứa dữ liệu mutable theo Context, điều gì có thể làm?
A. Luôn chép mọi field Context vào mỗi State
B. Bỏ interface vì chỉ còn một instance State
C. Chia sẻ instance State nếu bảo đảm an toàn
D. Luôn phải khởi tạo State mới cho từng thao tác
Đáp án đúng: C

Khi nghiệp vụ cần lưu trạng thái sau thao tác chuyển, điều gì quan trọng?
A. Để lớp giao diện tự quyết định commit mọi dữ liệu
B. Chỉ cập nhật field Java mà không ghi dữ liệu xuống DB
C. Ghi trạng thái mới trước rồi bỏ mọi lỗi cập nhật
D. Đồng bộ thay đổi nghiệp vụ với trạng thái đã lưu
Đáp án đúng: D

Kiểm thử chuyển trạng thái nên ưu tiên trường hợp nào?
A. Chỉ khởi tạo State object rồi kiểm tra không null
B. Chỉ đếm số class hiện thực State interface
C. Chỉ so thời gian khởi tạo Context trong JVM
D. Cạnh chuyển hợp lệ và cạnh bị cấm từ mỗi state
Đáp án đúng: D

Điểm khác nhau hữu ích giữa State và Strategy là gì?
A. Strategy yêu cầu Context có sơ đồ chuyển trạng thái
B. State bắt buộc dùng observer để thay hành vi
C. State theo vòng đời trạng thái; Strategy chọn cách làm
D. State chỉ dùng cho UI; Strategy chỉ dùng cho database
Đáp án đúng: C

Mục tiêu khi thay khối if/switch trạng thái dài bằng State Pattern là gì?
A. Đưa hành vi riêng của state vào các lớp tương ứng
B. Để Context tự suy ra hành vi từ tên class State
C. Đưa toàn bộ logic sang một switch tại controller
D. Chuyển mọi nhánh sang file JSON nhưng giữ nguyên mã
Đáp án đúng: A

Khi lưu một State rồi khôi phục sau restart, cần chú ý điều gì?
A. Lưu nguyên tham chiếu object Java rồi dùng giữa các JVM
B. Khôi phục trực tiếp mọi thread đang chạy trước khi tắt
C. Ánh xạ state đã lưu sang loại hợp lệ khi nạp
D. Tự cho phép mọi transition từ state vừa nạp
Đáp án đúng: C

Hai thread cùng chuyển State của một Context, rủi ro nào cần xử lý?
A. Từng State tự tạo transaction phân tán mặc định
B. Race condition giữa kiểm tra và cập nhật State
C. Đọc State sẽ luôn nhận bản sao bất biến tự động
D. Mọi thao tác sẽ tự chạy tuần tự nhờ State interface
Đáp án đúng: B

Khi thêm một trạng thái mới, việc kiểm tra nào đặc biệt cần thiết?
A. Bỏ kiểm thử các trạng thái đã có trước
B. Rà các cạnh chuyển và luật nghiệp vụ liên quan
C. Chỉ đổi tên class Context sang tên mới
D. Chỉ thêm State vào package là đủ mọi luồng
Đáp án đúng: B

Khi test Context ủy quyền cho State, assertion nào có ý nghĩa?
A. Hành vi quan sát và State sau lệnh đúng kỳ vọng
B. Chỉ số lượng import của mỗi Concrete State
C. Chỉ xác nhận Context có một biến kiểu interface
D. Chỉ xem tên method của State không bị trùng
Đáp án đúng: A
