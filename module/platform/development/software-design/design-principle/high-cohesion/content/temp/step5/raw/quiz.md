Một lớp có High Cohesion thường có đặc điểm nổi bật nào?
A. Dữ liệu và method cùng phục vụ một trách nhiệm
B. Nhiều nhóm method ít liên hệ chỉ để giảm số lớp
C. Các field được mở public cho module khác sử dụng
D. Method làm nhiều chức năng độc lập dùng chung DB
Đáp án đúng: A

InvoiceManager tính tổng tiền, kết nối SMTP và tạo PDF; dấu hiệu thiết kế nào rõ nhất?
A. Nhiều lý do thay đổi nằm trong cùng một lớp
B. Các hành vi dùng chung một giao diện thống nhất
C. Tất cả method đều sử dụng cùng một loại dữ liệu
D. Một object cần thêm nhiều constructor để khởi tạo
Đáp án đúng: A

Method tính hạn mức nằm trong PaymentService nhưng đọc hầu hết field của Customer; nên xét gì?
A. Cho PaymentService kế thừa trực tiếp Customer
B. Giữ method tại chỗ và thêm getter cho mọi field
C. Sao chép các field Customer vào PaymentService
D. Move Method về Customer nếu phù hợp trách nhiệm
Đáp án đúng: D

Một class xử lý đơn hàng lẫn định dạng báo cáo có hai cụm method rõ rệt; refactor nào hợp lý?
A. Extract Class tách riêng phần định dạng báo cáo
B. Thêm field static để hai cụm sử dụng chung
C. Đưa cả hai trách nhiệm vào một lớp cha mới
D. Gộp mọi method thành một hàm xử lý đơn
Đáp án đúng: A

Trong một hàm Java, dấu hiệu cohesion thấp nào đáng chú ý?
A. Hàm kiểm tra từng điều kiện của một quy tắc
B. Hàm biến đổi một DTO theo một hợp đồng
C. Hàm tính tổng của các dòng hóa đơn hợp lệ
D. Hàm trộn xử lý input, gửi email và lưu DB
Đáp án đúng: D

Khi gom method thành module, tiêu chí nào giúp tăng cohesion?
A. Gom method theo số dòng code tương tự
B. Gom tất cả lớp dùng chung thư viện logging
C. Gom theo năng lực và trách nhiệm liên quan
D. Gom mọi thao tác được gọi trong một request
Đáp án đúng: C

Lớp chỉ đổi vì luật tính giá, không vì thay đổi giao diện; điều này hỗ trợ điều gì?
A. Hệ thống không còn cần interface giữa các lớp
B. Class có thể bỏ kiểm tra bất biến khi tính toán
C. Thay đổi tập trung hơn vào một nhóm trách nhiệm
D. Mọi module phía ngoài đều tự sửa theo luật tính giá
Đáp án đúng: C

Một object liên tục đọc nhiều field của object khác để tính toán; đây là gợi ý nào?
A. Feature Envy: cân nhắc Move Method về chủ dữ liệu
B. High Cohesion vì hai object giao tiếp thường xuyên
C. Open/Closed vì tránh cập nhật class đang gọi
D. Interface Segregation vì cần thêm method đọc
Đáp án đúng: A

Tách phần tạo báo cáo khỏi OrderService giúp unit test thế nào?
A. Test OrderService phải chạy đúng sau test tạo PDF
B. Mỗi nhóm hành vi có bộ fixture và assertion riêng
C. Mọi test sẽ không cần dữ liệu đầu vào nghiệp vụ
D. Test tạo báo cáo bắt buộc khởi động cả HTTP server
Đáp án đúng: B

Khi tách class thành nhiều class siêu nhỏ, rủi ro thực tế là gì?
A. Tất cả dependency sẽ tự biến mất sau refactor
B. Logic phân mảnh và tăng chi phí điều phối
C. Mọi interface đều được Java tự tạo implementation
D. Mọi class tự có cohesion cao dù không rõ chức năng
Đáp án đúng: B

Lớp nhận thay đổi khi sửa quy tắc thuế lẫn khi sửa mẫu email; nên xem xét gì?
A. Giữ nguyên class vì vẫn cùng một luồng nghiệp vụ
B. Cho lớp kế thừa thêm EmailFormatter để tái dùng
C. Tách trách nhiệm vì có các lý do thay đổi khác nhau
D. Chuyển toàn bộ method vào một utility static
Đáp án đúng: C

Một nhóm các method cùng kiểm tra bất biến của Order nên đặt ở đâu?
A. Trong mỗi client để có tùy chỉnh kiểm tra riêng
B. Gần dữ liệu Order để tạo một trách nhiệm nhất quán
C. Trong REST controller vì request đưa dữ liệu vào
D. Trong module email vì cần gửi kết quả kiểm tra
Đáp án đúng: B

Muốn đánh giá việc Move Method có phù hợp, nên quan sát chỉ dấu nào?
A. Method được gọi từ nhiều lớp thuộc cùng package
B. Method có nhiều câu lệnh return trong cùng hàm
C. Method có tên dài hơn đa số method đang có
D. Method dùng dữ liệu của lớp đích nhiều hơn lớp hiện tại
Đáp án đúng: D

Trong thiết kế dịch vụ, boundary nào thường gắn kết hơn?
A. Các operation cùng đọc bảng users nhưng khác chức năng
B. Các operation phục vụ một năng lực nghiệp vụ rõ ràng
C. Các operation dùng chung thư viện xử lý HTTP
D. Các operation có cùng số tham số trong request
Đáp án đúng: B

Khi refactor để tăng cohesion, cần bảo vệ điều gì bằng test?
A. Mọi class sau refactor phải dùng chung một base
B. Thứ tự dòng code nội bộ không được thay đổi
C. Số lượng method private trong lớp phải giữ nguyên
D. Hành vi quan sát và các bất biến nghiệp vụ hiện có
Đáp án đúng: D

Cohesion cao và coupling thấp cùng mang lại lợi ích nào khi bảo trì?
A. Mọi thay đổi tự tương thích khi đổi định dạng dữ liệu
B. Có thể bỏ toàn bộ integration test của hệ thống
C. Thay đổi thường gói trong trách nhiệm và ít lan rộng
D. Các subsystem trở nên không cần contract cộng tác
Đáp án đúng: C
