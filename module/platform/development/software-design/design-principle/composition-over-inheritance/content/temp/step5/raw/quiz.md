Một dịch vụ gửi email hoặc SMS tùy cấu hình lúc chạy nên kết hợp hành vi thế nào?
A. Cho service kế thừa trực tiếp lớp EmailClient
B. Giữ Channel interface rồi ủy quyền lời gọi gửi
C. Dùng phương thức static chọn client theo tên
D. Tạo lớp con tương ứng cho mọi cấu hình kênh gửi
Đáp án đúng: B

Quan hệ nào phân biệt đúng has-a với is-a trong thiết kế đối tượng?
A. Car kế thừa Engine; Sedan chứa một Car
B. Car chứa Engine; Sedan là một loại Car
C. Engine kế thừa Car; Sedan chứa Engine
D. Sedan kế thừa Engine; Car chứa Sedan
Đáp án đúng: B

Khi kết hợp ba tính năng tùy chọn bằng kế thừa, rủi ro nào dễ xuất hiện?
A. Phải khởi tạo đối tượng qua constructor
B. Cần thêm các interface cho lớp cộng tác
C. Nhiều lớp con cho các tổ hợp tính năng
D. Đối tượng khó chia sẻ chung một contract
Đáp án đúng: C

OrderService kế thừa SqlRepository chỉ để dùng save(); cách tái cấu trúc nào tốt hơn?
A. OrderService chứa Repository port để gọi save
B. Đưa thao tác save vào mọi lớp con của Service
C. Cho OrderService truy cập trực tiếp bảng SQL
D. Cho SqlRepository kế thừa lại OrderService
Đáp án đúng: A

Khi nào kế thừa có thể phù hợp hơn một lớp delegate bổ sung?
A. Hai lớp chỉ cùng sử dụng một tiện ích nhỏ
B. Subtype thay thế đúng trong quan hệ is-a
C. Một lớp cần gọi API của lớp khác lúc chạy
D. Hai tính năng độc lập cần kết hợp linh hoạt
Đáp án đúng: B

Một unit test thay thuật toán giá bằng fake dễ thực hiện nhất khi thiết kế nào?
A. Tiêm PricingPolicy qua interface vào service
B. PricingService chọn policy từ biến static
C. PricingService tự tạo DefaultPricingPolicy
D. PricingService kế thừa một policy cụ thể
Đáp án đúng: A

Strategy và Decorator khác nhau thế nào về cách dùng composition?
A. Decorator chỉ chọn một thuật toán ở startup
B. Cả hai đều buộc sửa source object gốc
C. Strategy luôn kế thừa lớp client chính
D. Strategy đổi thuật toán; Decorator thêm hành vi
Đáp án đúng: D

Trong Bridge, hai chiều biến đổi độc lập nên được thiết kế ra sao?
A. Tách abstraction và implementor bằng interface
B. Cho abstraction kế thừa mọi implementation
C. Đặt mọi biến thể vào một switch của client
D. Tạo lớp con cho từng cặp biến thể cụ thể
Đáp án đúng: A

Lớp con sửa field protected của lớp cha khiến thay đổi dễ lan truyền; nên làm gì?
A. Đưa dữ liệu dùng chung vào một singleton
B. Chuyển mọi field protected thành public field
C. Dời hành vi vào collaborator có API đóng gói
D. Cho lớp con truy cập thêm nội bộ lớp khác
Đáp án đúng: C

Chi phí thực tế cần cân nhắc khi ưu tiên composition là gì?
A. Thêm object cộng tác và bước cấu hình/ủy quyền
B. Không thể thay implementation tại thời gian chạy
C. Mỗi delegate bắt buộc có một thread riêng
D. Mất hoàn toàn khả năng tái sử dụng interface
Đáp án đúng: A

Muốn thay implementation JDBC bằng fake khi kiểm thử, phụ thuộc nên hướng vào đâu?
A. Một lớp JdbcRepository được new trực tiếp
B. Một singleton chứa toàn bộ JDBC Connection
C. Một lớp cha cơ sở chứa câu lệnh SQL
D. Interface Repository do phía sử dụng định nghĩa
Đáp án đúng: D

Ghép logging và nén dữ liệu bằng Decorator cần giữ điều gì?
A. Các wrapper buộc đổi chữ ký của API gốc
B. Mỗi wrapper bắt buộc kế thừa concrete object
C. Các wrapper theo cùng interface; chú ý thứ tự
D. Client gọi riêng từng wrapper không cần delegate
Đáp án đúng: C

Trong mô hình đơn hàng dùng chính sách tính thuế, quan hệ nào hợp lý?
A. TaxPolicy kế thừa Order để biết giá trị
B. Order tạo một lớp con mới cho từng chính sách thuế
C. Order kế thừa TaxPolicy chỉ để gọi calculate
D. Order có TaxPolicy collaborator để tính thuế
Đáp án đúng: D

Một lớp cha phình to với nhiều nhánh cho từng loại thanh toán; hướng refactor nào tốt?
A. Thêm các field protected vào mọi lớp con
B. Đẩy tất cả nhánh vào constructor lớp cha
C. Tách PaymentBehavior và ủy quyền xử lý
D. Sao chép logic thanh toán sang mỗi lớp con
Đáp án đúng: C

Vì sao không nên áp dụng composition máy móc cho mọi quan hệ?
A. Mọi hệ phân cấp kế thừa đều là lỗi thiết kế
B. Composition luôn vi phạm tính đóng gói dữ liệu
C. Delegate khiến interface không thể kiểm thử
D. Kế thừa vẫn hữu ích cho subtype đúng LSP
Đáp án đúng: D

Khi cần đổi collaborator giữa nhiều request đồng thời, cần lưu ý gì?
A. Tạo mới collaborator khi thread đang dùng nó
B. Quản lý vòng đời và đồng bộ khi hoán đổi
C. Bỏ contract vì từng request có trạng thái riêng
D. Cho mọi request tự ghi chung field không khóa
Đáp án đúng: B
