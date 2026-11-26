Trong Decorator, wrapper và đối tượng được bọc liên hệ qua kiểu nào?
A. Cùng hợp đồng Component để thay thế được cho nhau
B. Wrapper kế thừa duy nhất lớp ứng dụng chính
C. Wrapper buộc triển khai API riêng không tương thích
D. Đối tượng gốc phải import mọi loại wrapper
Đáp án đúng: A

Lời gọi tới Decorator thường được xử lý theo hướng nào?
A. Truy cập trực tiếp field private của đối tượng gốc
B. Chuyển mọi lời gọi tới một singleton toàn cục
C. Thêm xử lý và ủy quyền đến Component bên trong
D. Bỏ qua Component để tự chạy tất cả nghiệp vụ
Đáp án đúng: C

Vì sao Decorator hữu ích khi cần ghép nhiều tính năng tùy chọn?
A. Loại bỏ nhu cầu phân định hợp đồng phương thức
B. Tránh tạo nhiều lớp con cho mọi tổ hợp tính năng
C. Ép mỗi lớp con kế thừa hai lớp cơ sở cùng lúc
D. Buộc cập nhật source Component khi thêm tính năng
Đáp án đúng: B

Có hai decorator nén và mã hóa, thứ tự ghép có ảnh hưởng gì?
A. Mọi decorator luôn giao hoán với nhau tuyệt đối
B. Thứ tự có thể đổi dữ liệu và quy trình giải mã
C. Chỉ ảnh hưởng tên lớp, không đổi kết quả xử lý
D. JVM tự sắp xếp các wrapper theo kiểu dữ liệu
Đáp án đúng: B

Trong Java, một decorator thường giữ thành phần nào?
A. Một lớp con của mọi implementation hiện có
B. Một bản sao source của đối tượng được trang trí
C. Một bảng ánh xạ mọi instance đang chạy trong JVM
D. Một tham chiếu tới Component được bọc bên trong
Đáp án đúng: D

Khách hàng có thể thêm logging rồi metrics vào service khi nào?
A. Khi client gọi trực tiếp constructor implementation
B. Chỉ khi service có sẵn lớp con LoggingMetrics
C. Khi các wrapper cùng triển khai interface service
D. Chỉ khi tất cả wrapper được tạo lúc biên dịch
Đáp án đúng: C

Để giữ hợp đồng của Component, decorator nên tránh điều gì?
A. Thay đổi ý nghĩa trả về trái với interface gốc
B. Định tuyến lời gọi đến thành phần được bọc
C. Kiểm tra tham số như hợp đồng đã quy định
D. Bổ sung ghi log không làm đổi kết quả nghiệp vụ
Đáp án đúng: A

Khi một decorator bao hai decorator khác, lời gọi chạy theo thứ tự nào?
A. Luôn chạy các wrapper song song không đợi nhau
B. Theo tên class xếp theo thứ tự chữ cái
C. Luôn từ Component gốc ra ngoài bất kể lời gọi
D. Theo chuỗi wrapper bên ngoài vào trong và quay lại
Đáp án đúng: D

Khi ghép cache và kiểm soát quyền, điều gì cần xem xét?
A. Để cache tự quyết định danh tính người yêu cầu
B. Thứ tự wrapper để không trả dữ liệu vượt quyền
C. Đặt cache ngoài cùng luôn bảo đảm an toàn quyền
D. Bỏ kiểm tra quyền nếu kết quả đã nằm trong cache
Đáp án đúng: B

Một decorator thêm đo thời gian nên đặt logic kết thúc thế nào?
A. Chỉ ghi số đo khi lời gọi hoàn tất không exception
B. Nuốt mọi exception để số đo không bị gián đoạn
C. Chỉ đo thời điểm tạo wrapper, bỏ qua request
D. Dọn đo trong finally để bao gồm cả trường hợp lỗi
Đáp án đúng: D

Nếu decorator không gọi Component bên trong khi cần, nguy cơ nào xảy ra?
A. Mọi trạng thái decorator sẽ được JVM tự reset
B. Hành vi cốt lõi có thể bị bỏ qua ngoài ý muốn
C. Component tự triển khai phần logic bổ sung còn thiếu
D. Lời gọi sẽ được Java tự chuyển đến đối tượng gốc
Đáp án đúng: B

Một decorator quản lý resource được mở trong lời gọi cần chú ý gì?
A. Giải phóng resource cả khi lời gọi bên trong ném lỗi
B. Dùng finalize thay cho quy tắc đóng tài nguyên
C. Chỉ giải phóng resource nếu caller yêu cầu thêm
D. Giữ resource mở xuyên mọi request để tối ưu
Đáp án đúng: A

Client chỉ biết Component interface được lợi gì khi dùng Decorator?
A. Client phải ép kiểu lần lượt qua mọi wrapper
B. Client bắt buộc đọc source của decorator cụ thể
C. Có thể thay đổi chuỗi wrapper mà không sửa client
D. Client cần khởi tạo trực tiếp mọi lớp con của Component
Đáp án đúng: C

Muốn unit test một decorator ghi log mà không dùng service thật, nên làm gì?
A. Kiểm thử chỉ số dòng trong class decorator
B. Chạy toàn hệ thống rồi chỉ kiểm tra thời gian
C. Dùng fake Component để kiểm tra ủy quyền và log
D. Mock chính decorator để bỏ qua logic cần kiểm tra
Đáp án đúng: C

Ghép hàng chục decorator quanh lời gọi rất nhỏ có đánh đổi gì?
A. Bảo đảm mọi decorator được JVM hợp nhất thành một
B. Tự giảm thời gian xử lý vì thêm nhiều interface
C. Không còn phát sinh đối tượng trong heap Java
D. Tăng chi phí ủy quyền và khó theo dõi call chain
Đáp án đúng: D

Decorator chứa bộ đếm mutable dùng chung giữa thread cần làm gì?
A. Đồng bộ thích hợp hoặc dùng bộ đếm thread-safe
B. Dùng int bình thường vì decorator luôn có một thread
C. Thêm wrapper khác để tự loại bỏ mọi race condition
D. Bỏ unit test vì race chỉ xảy ra trên production
Đáp án đúng: A
