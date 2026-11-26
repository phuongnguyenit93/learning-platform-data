Unit test OrderService không được gửi email thật; nên thay thành phần nào?
A. Chính OrderService bằng mock, vẫn dùng cổng email thật
B. Toàn bộ controller bằng fake nhưng giữ SMTP thật
C. Đối tượng request bằng spy, vẫn gọi server email
D. Cổng gửi email bằng một test double kiểm soát được
Đáp án đúng: D

Khác biệt chính giữa stub và mock trong thiết kế test double là gì?
A. Stub định sẵn phản hồi; mock hỗ trợ xác minh tương tác
B. Stub bắt buộc spy đối tượng; mock luôn gọi method thật
C. Stub xác minh số lần gọi; mock chỉ cung cấp hằng số
D. Stub luôn đọc database; mock chỉ lưu dữ liệu trong RAM
Đáp án đúng: A

Một fake repository dùng cho unit test thường có đặc điểm nào?
A. Luôn chuyển request tới cơ sở dữ liệu production thật
B. Dùng logic lưu RAM thay thế cơ sở dữ liệu
C. Chỉ ghi lại mọi lời gọi mà không có logic lưu trữ
D. Chỉ trả các giá trị mặc định do framework sinh ra
Đáp án đúng: B

Mockito spy khác mock thuần ở điểm nào thường gặp?
A. Spy luôn chặn mọi method và không giữ trạng thái thật
B. Spy bọc đối tượng thật nên method có thể chạy thật
C. Spy chỉ dùng được cho interface chưa có implementation
D. Spy thay thế các assertion bằng số lần gọi mặc định
Đáp án đúng: B

Trong Mockito, `when(repo.find(id)).thenReturn(user)` nhằm làm gì?
A. Bắt mọi method của repo trả cùng một user
B. Kiểm tra user được lưu vào database thực
C. Thiết lập kết quả cho lời gọi repo.find(id)
D. Chỉ kiểm tra repo.find(id) đã được gọi một lần
Đáp án đúng: C

Muốn mô phỏng một void method ném lỗi qua Mockito, hướng nào phù hợp?
A. Dùng `assertDoesNotThrow` để làm mock ném lỗi
B. Dùng `thenReturn(exception)` cho phương thức void
C. Gọi `verify(mock)` trước khi stub phương thức send
D. Dùng `doThrow(...).when(mock).send(...)`
Đáp án đúng: D

Khi stub method có hai tham số và một tham số dùng anyString(), tham số kia nên xử lý sao?
A. Dùng matcher như eq(...) để nhất quán trong lời gọi
B. Dùng trực tiếp giá trị literal không có matcher
C. Bỏ tham số thứ hai vì Mockito tự suy ra giá trị
D. Thay cả hai tham số bằng null trước khi stubbing
Đáp án đúng: A

`ArgumentCaptor` giúp kiểm chứng điều gì sau khi service gọi repository?
A. Mã SQL mà driver JDBC tạo cho phương thức save
B. Giá trị mặc định của tất cả method mock khác
C. Giá trị đối tượng được truyền tới phương thức save
D. Tổng số thread chạy trong quá trình gọi save
Đáp án đúng: C

Khi cần xác nhận publish() gọi đúng một lần, lệnh Mockito nào phù hợp?
A. Dùng `spy(pub)` để tự tăng bộ đếm lời gọi
B. Dùng `verify(pub, times(1)).publish(event)`
C. Dùng `when(pub.publish(event)).thenReturn(1)`
D. Dùng `reset(pub)` trước khi kiểm tra tổng lượt gọi
Đáp án đúng: B

Muốn bảo đảm delete() chưa từng được gọi, cách verify nào phù hợp?
A. Dùng `when(repo.delete(id))` không thiết lập giá trị
B. Dùng `doReturn(false)` rồi tự suy ra không có gọi
C. Dùng `verify(repo, never()).delete(id)`
D. Dùng `verify(repo, atLeastOnce()).delete(id)`
Đáp án đúng: C

Với spy, vì sao `doReturn(x).when(spy).read()` có thể an toàn hơn `when(spy.read())`?
A. Cách when luôn tắt việc gọi method thật trên spy
B. Cách when luôn bỏ qua toàn bộ exception do spy ném
C. Cách doReturn tự xóa mọi interaction đã ghi nhận
D. Cách doReturn tránh chạy method thật trong lúc stub
Đáp án đúng: D

Unit test verify quá nhiều method nội bộ của collaborator có rủi ro gì?
A. Test loại bỏ nhu cầu so kết quả quan sát được
B. Test luôn phát hiện được mọi lỗi nghiệp vụ mới
C. Test sẽ tự đánh dấu các collaborator là final
D. Test dễ vỡ khi refactor dù hành vi vẫn đúng
Đáp án đúng: D

Nên stub repository thế nào khi unit test service cần một user có sẵn?
A. Stub findById trả user, còn kiểm thử hành vi service
B. Mock luôn chính service và bỏ qua logic cần kiểm thử
C. Để repo gọi database thật rồi gắn tên unit test
D. Stub từng private method của service qua reflection
Đáp án đúng: A

Khi refactor thay đổi cách gọi collaborator nhưng kết quả vẫn đúng, test nên ưu tiên gì?
A. Ép private method phải được gọi đúng số lần
B. Khẳng định kết quả công khai và tương tác quan trọng
C. Bỏ assertion kết quả và chỉ verify mọi lời gọi
D. Kiểm tra nguyên thứ tự từng method nội bộ
Đáp án đúng: B

Để các unit test không ảnh hưởng nhau qua trạng thái mock, nên tổ chức thế nào?
A. Cho từng test thay đổi stub do test khác cấu hình
B. Dùng một static mock cho toàn bộ test trong module
C. Tạo mock riêng cho mỗi test và tránh state chia sẻ
D. Reset mock ở cuối suite nhưng cho mọi test dùng chung
Đáp án đúng: C

Khi verify rằng method được gọi với đối số null, matcher nào đúng?
A. Dùng `isNull()` để kiểm tra đối số là null
B. Dùng `anyString()` để chấp nhận cả giá trị null
C. Dùng `notNull()` để bao gồm cả giá trị null
D. Dùng `eq("")` để coi chuỗi rỗng là giá trị null
Đáp án đúng: A
