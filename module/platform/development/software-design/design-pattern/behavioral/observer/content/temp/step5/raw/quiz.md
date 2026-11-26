Trong Observer, khi subject đổi trạng thái, cơ chế nào được sử dụng?
A. Mỗi listener đọc định kỳ mọi biến của subject
B. Subject thông báo cho các listener đã đăng ký
C. Subject chỉ gọi một listener được chọn lúc build
D. Mọi listener cập nhật lẫn nhau theo chuỗi kế thừa
Đáp án đúng: B

Một listener muốn nhận sự kiện từ subject cần thao tác nào?
A. Sửa trực tiếp danh sách listener trong source
B. Đăng ký qua cơ chế subscribe hoặc addListener
C. Gọi notify mà không lưu thông tin đăng ký
D. Tạo bản sao của subject rồi dùng đối tượng riêng
Đáp án đúng: B

Khi màn hình đóng, cách quản lý observer nào giảm rò rỉ bộ nhớ?
A. Hủy đăng ký listener khi không còn sử dụng
B. Chỉ dừng render nhưng giữ subscription vô hạn
C. Giữ listener trong danh sách global để tái dùng
D. Tạo thêm subject mới mà không dọn listener cũ
Đáp án đúng: A

Muốn listener biết giá trị mới mà không đọc lại subject, nên thiết kế gì?
A. Chỉ phát tín hiệu không kèm ngữ cảnh thay đổi
B. Bắt listener truy vấn lại mọi thuộc tính từ đầu
C. Gửi dữ liệu liên quan trong event payload
D. Truyền trực tiếp toàn bộ bộ nhớ của subject
Đáp án đúng: C

Vì sao nên giữ event payload bất biến sau khi phát?
A. Giúp subject tự xóa mọi subscriber khi phát xong
B. Bắt listener chỉ được trả về dữ liệu bất biến
C. Đảm bảo mọi listener đều chạy trên cùng một lõi
D. Tránh listener khác sửa dữ liệu mà bên sau nhận
Đáp án đúng: D

Với notification đồng bộ, listener chậm có thể gây tác động nào?
A. Kéo dài thời gian thực thi lệnh phát sự kiện
B. Cho phép subject bỏ qua toàn bộ listener còn lại
C. Tự động tăng số worker chạy trong JVM
D. Làm thông báo được gửi trước khi đổi trạng thái
Đáp án đúng: A

Một listener ném exception trong vòng lặp notify có thể gây điều gì?
A. Tự động tạo retry riêng cho mọi listener khác
B. Không ảnh hưởng tới subject trong mọi triển khai
C. Buộc Java hoàn tác trạng thái subject đã đổi
D. Ngắt việc thông báo nếu thiếu chính sách cách ly lỗi
Đáp án đúng: D

Khi nhiều thread đăng ký và phát thông báo, cần quan tâm gì?
A. Giữ một Iterator dùng chung cho mọi thread
B. Chỉ giảm số lần notify mà không đồng bộ dữ liệu
C. Duyệt danh sách listener an toàn khi đồng thời sửa
D. Cho mọi thread trực tiếp chỉnh ArrayList không khóa
Đáp án đúng: C

CopyOnWriteArrayList thường thích hợp cho registry listener khi nào?
A. Một subject cần ghi dữ liệu trên cùng buffer mutable
B. Có hàng triệu lần thêm xóa listener mỗi giây
C. Mọi listener đều giữ một kết nối database riêng
D. Ít thay đổi đăng ký nhưng duyệt danh sách nhiều
Đáp án đúng: D

Khi chuyển thông báo sang hàng đợi bất đồng bộ, giả định nào cần xem xét lại?
A. Mọi listener sẽ hoàn tất trước khi publish trả về
B. Cập nhật trạng thái subject tự bị rollback
C. Mỗi listener mặc định nhận chính xác một thông báo
D. Thứ tự và thời điểm nhận không tự được đảm bảo
Đáp án đúng: D

Một listener phát sinh thêm thay đổi lên chính subject đang notify; nguy cơ gì?
A. Thông báo lồng nhau gây vòng gọi hoặc trạng thái khó đoán
B. Mọi sự kiện trước đó luôn được gộp thành một
C. Hệ thống tự đảm bảo không có đệ quy sự kiện
D. Listener sẽ tự bị xóa khỏi danh sách subscription
Đáp án đúng: A

Vì sao không nên coi việc subscribe là đã nhận được trạng thái hiện tại?
A. Observer chỉ hoạt động nếu subject chưa có dữ liệu
B. Đăng ký chỉ cam kết cập nhật sau đó nếu có phát
C. Mọi subject luôn tự gửi snapshot ngay khi đăng ký
D. Subscribe tự khóa mọi lần cập nhật trạng thái
Đáp án đúng: B

Muốn kiểm thử notify sau khi subject cập nhật, assertion nào tốt?
A. Chỉ kiểm tra tên lớp listener có chứa Observer
B. Chỉ đếm số method public của đối tượng subject
C. Listener giả nhận đúng event và dữ liệu cần thiết
D. Chỉ xác nhận subject đã khởi tạo thành công
Đáp án đúng: C

Một test cho unsubscribe cần xác minh điều gì?
A. Subject luôn xóa dữ liệu trạng thái khi bỏ listener
B. Tất cả listener khác cũng bị hủy đăng ký theo
C. Listener bị gỡ không nhận sự kiện phát sau đó
D. Listener vẫn nhận ít nhất một event sau khi gỡ
Đáp án đúng: C

So với Mediator, nhiệm vụ đặc trưng của Observer là gì?
A. Lưu snapshot nội tại để hỗ trợ thao tác undo
B. Phân phối thông báo thay đổi cho nhiều subscriber
C. Điều phối mọi quy tắc tương tác giữa các colleague
D. Đóng gói chiến lược chọn thuật toán theo trạng thái
Đáp án đúng: B

Khi listener gắn với tài nguyên cần giải phóng, thiết kế nào phù hợp?
A. Quy định rõ vòng đời đăng ký và bước hủy đăng ký
B. Giữ subscription sống cho đến khi JVM tự thoát
C. Coi listener sẽ tự biến mất nếu không render UI
D. Để callback mở thêm tài nguyên sau mỗi lần notify
Đáp án đúng: A
