Cần lấy ID của VPC đã tồn tại trên cloud nhưng không muốn Terraform quản lý vòng đời VPC đó; cách khai báo nào phù hợp nhất?
A. Import VPC vào state để quản lý toàn bộ cấu hình của nó.
B. Dùng data source để tra cứu VPC mà không nhận quản lý vòng đời.
C. Tạo resource VPC mới rồi thay ID bằng ID VPC hiện có.
D. Dùng output ở root module để truy vấn VPC trực tiếp từ provider.
Đáp án đúng: B

Một nhóm muốn các máy CI dùng cùng phiên bản provider đã kiểm thử khi chạy Terraform; tổ hợp biện pháp nào phù hợp nhất?
A. Chỉ khóa phiên bản Terraform CLI và để provider tự nâng cấp.
B. Khóa phiên bản module nhưng luôn tải provider mới nhất.
C. Chỉ ghi phiên bản provider trong tài liệu và kiểm tra thủ công.
D. Khai báo version constraint và commit tệp .terraform.lock.hcl.
Đáp án đúng: D

Terraform thường xác định phụ thuộc ngầm giữa hai resource bằng thông tin nào trong HCL?
A. Tham chiếu thuộc tính resource này trong biểu thức resource kia.
B. Thứ tự khai báo các resource trong cùng một tệp cấu hình.
C. Tên resource được đặt theo thứ tự tạo mong muốn của nhóm.
D. Việc các resource dùng chung một cấu hình provider.
Đáp án đúng: A

Danh sách máy chủ có thể đổi thứ tự nhưng mỗi máy có mã định danh ổn định; cách lặp nào giúp duy trì địa chỉ resource ít bị xáo trộn nhất?
A. Dùng count theo vị trí phần tử trong danh sách đầu vào.
B. Dùng count với số lượng cố định cho toàn bộ các máy chủ.
C. Dùng for_each với tên hiển thị có thể đổi sau mỗi lần tái triển khai.
D. Dùng for_each trên map khóa bằng mã định danh ổn định của máy.
Đáp án đúng: D

Để xây dựng module Terraform dùng chung cho nhiều nhóm và môi trường, thiết kế nào giúp hạn chế phụ thuộc ngầm nhất?
A. Cho module đọc trực tiếp state của mọi môi trường triển khai.
B. Sao chép nội dung module vào từng root để sửa theo nhu cầu.
C. Gắn cứng region, VPC và tên môi trường trong module dùng chung.
D. Khai báo input, output rõ ràng và phát hành module theo phiên bản.
Đáp án đúng: D

Khi plan dự kiến thay thế database có dữ liệu nhưng chưa được phê duyệt, cơ chế nào chặn thao tác hủy nếu resource vẫn còn khai báo?
A. Khai báo ignore_changes cho mọi output ID của database.
B. Đặt prevent_destroy trong lifecycle của resource database.
C. Đặt depends_on đến resource snapshot để chặn mọi thao tác hủy.
D. Đánh dấu biến tên database là sensitive trong root module.
Đáp án đúng: B

Hai pipeline có thể chạy terraform apply đồng thời trên cùng một môi trường; cách nào ngăn ghi đè state do cạnh tranh?
A. Dùng chung workspace nhưng tắt locking để giảm thời gian chờ.
B. Giữ state riêng trên từng runner rồi gộp lại sau khi apply.
C. Dùng remote backend hỗ trợ khóa state và tuần tự hóa lượt apply.
D. Commit state vào Git rồi dùng merge conflict để kiểm soát ghi.
Đáp án đúng: C

Biến mật khẩu đã được khai báo sensitive = true trong Terraform; nhận định nào đúng về dữ liệu trong state?
A. Giá trị được mã hóa riêng bởi sensitive trước khi ghi vào state.
B. Giá trị không thể xuất hiện trong state sau khi resource tạo xong.
C. Giá trị chỉ có trong plan và tự biến mất khỏi state sau apply.
D. Giá trị vẫn có thể nằm trong state nên phải bảo vệ backend.
Đáp án đúng: D

Muốn tách quyền và giới hạn rủi ro thao tác nhầm giữa dev và production, cách tổ chức state nào phù hợp nhất?
A. Dùng một state chung nhưng đặt tiền tố khác nhau cho resource.
B. Tách state và quyền truy cập backend cho từng môi trường.
C. Dùng một workspace duy nhất, đổi biến theo tài khoản người chạy.
D. Dùng một provider có quyền admin chung cho tất cả môi trường.
Đáp án đúng: B

Một quản trị viên đổi cấu hình tài nguyên trực tiếp trên console; cách nào xem thay đổi cần phản ánh vào state mà chưa sửa lại tài nguyên thật?
A. Chạy terraform validate để tải trạng thái thực và đối chiếu.
B. Chạy terraform fmt để so cấu hình HCL với cấu hình trên cloud.
C. Chạy terraform plan -refresh-only để xem thay đổi state dự kiến.
D. Chạy terraform providers lock để tìm khác biệt ngoài cấu hình.
Đáp án đúng: C

Một máy chủ đã được tạo thủ công đang hoạt động; muốn Terraform quản lý máy đó mà không tạo thêm máy mới, thao tác nào phù hợp nhất?
A. Chỉ thêm resource block rồi apply để Terraform tự tìm máy cũ từ ID.
B. Khai báo resource và import đối tượng thực vào địa chỉ tương ứng.
C. Dùng data source rồi Terraform tự cấp quyền cập nhật máy cũ.
D. Đưa ID máy vào output block và chạy refresh để nhận quản lý.
Đáp án đúng: B

Cần chuyển một resource đang quản lý từ root vào module mà không thay thế tài nguyên thực; cơ chế nào biểu diễn việc đổi địa chỉ?
A. Khai báo moved block với địa chỉ cũ và địa chỉ mới của resource.
B. Thêm depends_on tới module để giữ nguyên ID và địa chỉ resource cũ.
C. Đánh dấu resource bị taint trước khi chuyển sang module mới.
D. Đổi tên block trong HCL rồi apply để Terraform tự suy đoán.
Đáp án đúng: A

Trong pipeline triển khai production, cách nào bảo đảm terraform apply dùng đúng bản plan đã qua phê duyệt?
A. Lưu plan thành tệp đã duyệt và dùng chính tệp đó khi apply.
B. Chạy lại plan trên nhánh mới nhất rồi apply không cần xem lại.
C. So sánh số lượng file HCL trước khi cho phép lệnh apply chạy.
D. Dùng apply -auto-approve với các biến môi trường được bảo vệ.
Đáp án đúng: A

Khi phát hành module Terraform dùng chung, biện pháp nào kiểm tra các kỳ vọng về output qua nhiều bộ input trước khi triển khai thật?
A. Dùng terraform fmt để đánh giá tính đúng đắn của output.
B. Dùng terraform init để thực thi assertions cho từng bộ input.
C. Dùng terraform test với nhiều case và assertions về output.
D. Dùng terraform output dù cấu hình chưa có state được tạo.
Đáp án đúng: C

Một hệ thống ngoài Terraform tự cập nhật một trường tag, còn các thuộc tính khác vẫn do Terraform quản lý; cách hạn chế plan nhiễu nào phù hợp?
A. Đặt prevent_destroy để Terraform bỏ qua mọi cập nhật tag.
B. Đặt depends_on đến hệ thống cập nhật tag ở ngoài Terraform.
C. Dùng lifecycle ignore_changes cho đúng trường tag bên ngoài sửa.
D. Dùng replace_triggered_by để ngăn Terraform cập nhật trường tag.
Đáp án đúng: C

Một nhóm đang có local state quản lý hạ tầng thật và muốn chuyển sang remote backend; trình tự nào giảm rủi ro mất liên kết state nhất?
A. Sao lưu state, cấu hình backend rồi init -migrate-state có kiểm soát.
B. Xóa local state, thêm remote backend rồi apply lại toàn bộ hạ tầng.
C. Commit local state lên Git để pipeline cùng dùng qua từng lần merge.
D. Chạy apply -refresh-only để Terraform tự di chuyển state sang backend mới.
Đáp án đúng: A
