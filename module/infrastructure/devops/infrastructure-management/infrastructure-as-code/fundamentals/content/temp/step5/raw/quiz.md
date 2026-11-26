Câu 1: Nhóm cần tái tạo hạ tầng nhất quán giữa dev và prod. Cách mô tả nào thể hiện rõ nhất Infrastructure as Code theo kiểu khai báo?
A. Ghi chuỗi lệnh tạo tài nguyên theo từng bước.
B. Ghi lại các lần thao tác bằng giao diện quản trị.
C. Mô tả trạng thái tài nguyên mong muốn bằng mã.
D. Lưu ảnh chụp màn hình hạ tầng hiện có.
Đáp án đúng: C

Câu 2: Sau khi IaC đưa hệ thống về cấu hình yêu cầu, mã và hạ tầng đều không đổi. Lần lập kế hoạch tiếp theo biểu hiện tính idempotent ra sao?
A. Đề nghị tạo lại resource để xác nhận cấu hình.
B. Không đề xuất thêm thay đổi tài nguyên nào.
C. Chạy lại mọi lệnh tạo và xóa tài nguyên cũ.
D. Tăng revision của resource sau mỗi lần chạy.
Đáp án đúng: B

Câu 3: Terraform tạo subnet và VM; cấu hình VM tham chiếu trực tiếp ID của resource subnet. Cơ chế nào xác lập thứ tự tạo hai tài nguyên?
A. Thứ tự tên file trong thư mục IaC.
B. Tham chiếu tạo phụ thuộc ngầm trong graph.
C. Vị trí khai báo resource ở cuối tập tin.
D. Số thứ tự provider trong tệp cấu hình.
Đáp án đúng: B

Câu 4: Một stack Terraform đã tạo các VM, subnet và bucket. State đóng vai trò cốt lõi gì khi chạy plan cho lần cập nhật kế tiếp?
A. Thay thế hệ thống monitor để kiểm tra VM.
B. Lưu lịch sử commit thay cho Git repository.
C. Giữ toàn bộ mật khẩu để bỏ qua IAM role.
D. Ánh xạ resource trong mã tới đối tượng đã quản lý.
Đáp án đúng: D

Câu 5: Hai pipeline CI đồng thời apply một stack IaC và cùng dùng state. Cấu hình nào giúp tránh xung đột cập nhật state?
A. Dùng remote backend có hỗ trợ khóa state.
B. Lưu state riêng ở runner nhưng cùng resource.
C. Lưu state vào Git và merge sau mỗi lần apply.
D. Cấp thêm quyền IAM cho cả hai pipeline.
Đáp án đúng: A

Câu 6: Biến mật khẩu DB được đánh dấu sensitive trong IaC. Thành phần nào vẫn cần bảo vệ vì có thể chứa giá trị nhạy cảm?
A. Chỉ tệp README giải thích cách chạy IaC.
B. Chỉ file khai báo biến không có giá trị.
C. Chỉ danh sách tên resource trong output.
D. State và plan artifact với mã hóa, hạn chế quyền.
Đáp án đúng: D

Câu 7: Plan cho thấy thay đổi subnet sẽ khiến DB bị replace thay vì cập nhật tại chỗ. Hành động nào phù hợp trước khi apply?
A. Rà tác động replace, sao lưu và duyệt plan.
B. Apply ngay vì plan được công cụ sinh tự động.
C. Xóa DB khỏi state để ngăn mất dữ liệu.
D. Tắt bước kiểm thử vì không đổi mã ứng dụng.
Đáp án đúng: A

Câu 8: Quản trị viên đã chỉnh quy tắc firewall qua console, nhưng mã IaC không thay đổi. Cách nào nhận diện drift trước khi sửa?
A. Chỉ xem diff giữa hai commit mã gần nhất.
B. Chỉ kiểm tra thời gian chạy pipeline CI.
C. Chạy plan đối chiếu với resource thực.
D. Đổi tên resource để ép công cụ tạo lại.
Đáp án đúng: C

Câu 9: Một bucket có dữ liệu đã được tạo thủ công, nay cần đưa vào quản lý IaC mà không tạo bucket mới. Cách làm nào phù hợp?
A. Khai báo bucket tên khác để tránh trùng ID.
B. Định nghĩa bucket rồi import vào state IaC.
C. Xóa bucket cũ rồi để IaC tạo lại bucket.
D. Sao chép object ra ngoài rồi tạo bucket khác.
Đáp án đúng: B

Câu 10: Các runner CI cài provider IaC mới nhất nên đôi khi plan thay đổi ngoài dự kiến. Điều gì tăng tính tái lập của triển khai?
A. Bật tự động nâng provider ở mọi lần chạy.
B. Chỉ cố định CLI, để provider tự nâng version.
C. Ràng buộc version provider và lưu dependency lock.
D. Chỉ đổi tên environment trước mỗi lần apply.
Đáp án đúng: C

Câu 11: Hai môi trường dev và prod dùng chung module Terraform nhưng không được ghi đè tài nguyên nhau. Thiết kế quản lý state nào phù hợp?
A. Cùng state nhưng thêm prefix dev/prod vào tag.
B. Để chung state và chỉ đổi biến output.
C. Tách state và IAM rõ ràng giữa dev/prod.
D. Để runner tự chọn tài nguyên theo tên branch.
Đáp án đúng: C

Câu 12: Ba đội tạo cùng kiến trúc web nhưng khác CIDR, kích thước máy và zone. Cách tổ chức mã IaC nào tăng tái sử dụng?
A. Dùng module versioned với input/output rõ ràng.
B. Sao chép toàn bộ resource và sửa ở mỗi repo.
C. Nhập tất cả resource vào một tệp chung lớn.
D. Đặt toàn bộ môi trường vào một state chung.
Đáp án đúng: A

Câu 13: Tổ chức muốn chặn quy tắc mạng mở cổng DB 5432 ra Internet, dù cấu hình IaC hợp lệ về cú pháp. Nên thêm kiểm soát nào?
A. Format check kiểm tra indent của file IaC.
B. State lock ngăn hai pipeline apply đồng thời.
C. Test tên resource phù hợp quy ước đặt tên.
D. Policy-as-code chặn plan vi phạm quy tắc.
Đáp án đúng: D

Câu 14: Pipeline IaC production cần giảm nguy cơ thay đổi ngoài ý muốn mà vẫn tự động hóa. Trình tự nào hợp lý nhất?
A. Validate, test, plan, phê duyệt rồi apply.
B. Apply trực tiếp, sau đó mới tạo plan để xem.
C. In secrets vào log để reviewer kiểm tra.
D. Bỏ duyệt plan nếu thay đổi đã qua Git.
Đáp án đúng: A

Câu 15: Một plan đã được duyệt buổi sáng, nhưng state thay đổi vì pipeline khác vừa apply. Nên xử lý như thế nào trước khi triển khai?
A. Dùng plan cũ và kiểm tra hạ tầng sau apply.
B. Đổi tên plan cũ để công cụ chấp nhận lại.
C. Bỏ bước refresh để giữ nội dung plan cũ.
D. Tạo plan mới từ state hiện có rồi duyệt.
Đáp án đúng: D

Câu 16: Cấu hình IaC đang quản lý một DB quan trọng; thay đổi tham số có nguy cơ ép thay thế DB. Biện pháp nào giảm rủi ro dữ liệu?
A. Bỏ tạo plan để tránh cảnh báo khó xử lý.
B. Dùng prevent_destroy, xét plan và có backup.
C. Xóa resource khỏi state trước lần apply mới.
D. Tăng timeout cho resource để tránh lỗi apply.
Đáp án đúng: B
