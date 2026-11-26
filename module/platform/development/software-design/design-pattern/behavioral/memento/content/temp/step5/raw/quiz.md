Memento giải quyết nhu cầu thiết kế nào mà không lộ chi tiết trạng thái?
A. Phân phối sự kiện đến mọi observer đã đăng ký
B. Đổi thuật toán xử lý khi object vào trạng thái mới
C. Lưu điểm khôi phục rồi phục hồi đối tượng
D. Ủy quyền tương tác của nhiều object cho mediator
Đáp án đúng: C

Trong Memento, Originator thường chịu trách nhiệm nào?
A. Quyết định lịch sử undo của toàn bộ ứng dụng
B. Giải mã dữ liệu từ mọi loại database khác nhau
C. Lưu danh sách các listener của sự kiện thay đổi
D. Tạo snapshot và khôi phục từ snapshot hợp lệ
Đáp án đúng: D

Vai trò của Caretaker trong mẫu Memento phù hợp nhất là gì?
A. Thay Originator quyết định các bất biến nghiệp vụ
B. Giữ các memento mà không sửa state bên trong
C. Đọc trực tiếp mọi field private của Originator
D. Tính lại trạng thái bằng cách gọi mọi operation
Đáp án đúng: B

Để snapshot không bị thay đổi sau khi lưu, thiết kế nào phù hợp?
A. Trả về trực tiếp collection mutable của Originator
B. Dùng memento bất biến với bản sao dữ liệu cần thiết
C. Giữ reference đến một buffer đang được cập nhật
D. Để Caretaker sửa nội dung snapshot theo thao tác
Đáp án đúng: B

Memento giữ tham chiếu đến List mutable của Originator có nguy cơ gì?
A. Snapshot cũ đổi theo khi List gốc bị sửa
B. State của Originator tự trở nên bất biến
C. Tự tạo bản deep copy cho mọi object trong List
D. Không thể tạo thêm snapshot sau lần lưu đầu
Đáp án đúng: A

Trước một thao tác chỉnh sửa có thể undo, thao tác nào giúp quay lại trạng thái cũ?
A. Đợi thao tác thành công mới tạo lịch sử rỗng
B. Chỉ ghi tên method sửa vào một logger
C. Xóa trạng thái trước rồi xây trạng thái mới
D. Lưu memento của trạng thái trước khi sửa
Đáp án đúng: D

Sau khi undo về trạng thái cũ rồi thực hiện chỉnh sửa mới, lịch sử redo thường xử lý sao?
A. Bỏ nhánh redo cũ vì lịch sử đã đổi hướng
B. Giữ nhánh redo cũ làm kết quả của sửa mới
C. Tự áp mọi thao tác redo trước khi sửa tiếp
D. Chuyển toàn bộ redo thành snapshot đầu tiên
Đáp án đúng: A

Khi snapshot đầy đủ quá lớn, cách nào có thể giảm chi phí lưu trữ?
A. Lưu mọi snapshot dưới dạng object đang mutable
B. Bắt mỗi memento giữ toàn bộ database trong RAM
C. Dùng delta hoặc checkpoint theo chu kỳ
D. Tăng số bản sao đầy đủ sau mỗi thao tác
Đáp án đúng: C

Một Originator có nhiều field, snapshot nên bao gồm phần nào?
A. Tất cả handle tài nguyên kể cả kết nối đang mở
B. State cần thiết để khôi phục hành vi hợp lệ
C. Chỉ tên class vì constructor có thể tái tạo hết
D. Chỉ các giá trị hiện ra trên giao diện người dùng
Đáp án đúng: B

Khi restore, tại sao cần xét toàn bộ bất biến trạng thái của Originator?
A. Để Caretaker tự tính lại mọi quy tắc nghiệp vụ
B. Để mọi field được đổi độc lập không cần điều kiện
C. Tránh tạo tổ hợp state không hợp lệ
D. Để thao tác restore luôn bỏ qua kiểm tra lỗi
Đáp án đúng: C

Memento và Command khác nhau ở cách hỗ trợ undo thường gặp nào?
A. Memento chỉ dùng đa luồng; Command chỉ dùng một luồng
B. Cả hai đều bắt buộc lưu toàn bộ graph object
C. Memento lưu state; Command có thể lưu thao tác
D. Memento luôn chạy lại SQL; Command chỉ dùng cho UI
Đáp án đúng: C

Kiểm thử undo của trình soạn thảo với Memento nên xác minh điều gì?
A. Caretaker có thể sửa field private của memento
B. Số lượng class thuộc dự án không tăng lên
C. Mọi lần restore đều khởi tạo một thread riêng
D. State sau restore khớp mốc đã lưu
Đáp án đúng: D

Khi hỗ trợ nhiều bước undo, Caretaker nên quản lý nội dung nào?
A. Mọi thuật toán validation của Originator
B. Chi tiết cách ánh xạ từng field thành SQL
C. Luồng sự kiện nội bộ từ mọi observer khác
D. Thứ tự các snapshot và vị trí lịch sử
Đáp án đúng: D

Nếu snapshot chứa thông tin nhạy cảm và được ghi xuống đĩa, cần xem xét gì?
A. Kiểm soát truy cập và bảo vệ dữ liệu lưu
B. Lưu trạng thái bằng chuỗi plain text công khai
C. Cho mọi module đọc memento để dễ debug
D. Chỉ đặt tên tệp khác là đủ để an toàn
Đáp án đúng: A

Khi phiên bản ứng dụng đổi schema trạng thái, memento lưu lâu cần giải pháp nào?
A. Version hoặc chuyển đổi định dạng khi khôi phục
B. Tự dùng snapshot chưa rõ cấu trúc như state mới
C. Bỏ qua mọi field mới và luôn restore không lỗi
D. Buộc caretaker sửa byte bên trong snapshot cũ
Đáp án đúng: A

Hai thread tạo và restore snapshot đồng thời, điều gì cần kiểm soát?
A. Chỉ tăng kích thước lịch sử để tránh race
B. Đồng bộ để snapshot và restore nhất quán
C. Tắt cơ chế sao chép snapshot của Originator
D. Để mỗi thread luôn dùng chung buffer đang sửa
Đáp án đúng: B
