Trong ứng dụng thanh toán Java, lớp PaymentService kế thừa trực tiếp HttpClient chỉ để tái sử dụng phương thức gửi request; khi thư viện HTTP thay đổi vòng đời kết nối, cả logic thanh toán cũng phải sửa dù quan hệ nghiệp vụ không phải là một loại HTTP client.
Hệ thống thương mại tạo các lớp Customer, PremiumCustomer và VIPCustomer để biểu diễn hạng hội viên; khi khách được nâng hoặc hạ hạng giữa phiên, chương trình phải thay đối tượng thay vì chỉ thay hành vi tính ưu đãi.
Ứng dụng mô phỏng động vật xây lớp Bird có phương thức fly và cho Penguin kế thừa; nhiều màn hình chỉ làm việc với Bird lại gặp lỗi khi gọi bay trên một loài không có khả năng đó.
Trong phần mềm quản lý xe, lớp Vehicle mặc định lưu nhiên liệu và thao tác đổ xăng; lớp ElectricVehicle kế thừa nhưng phải vô hiệu hóa nhiều phương thức, khiến các client xử lý Vehicle không còn dùng được một cách thống nhất.
Đội logistics tạo lớp con riêng cho từng tổ hợp gói giao hàng Nhanh/Thường và đối tác A/B/C; số lớp tăng theo tích số biến thể mỗi lần xuất hiện đối tác hoặc chính sách vận chuyển mới.
Hệ thống nhập dữ liệu có bốn định dạng file và ba chính sách kiểm tra dữ liệu; nhóm duy trì mười hai lớp con từ cùng một bộ đọc, khiến sửa logic kiểm tra chung phải cập nhật lặp lại nhiều lớp.
Ứng dụng báo cáo hỗ trợ PDF, CSV và HTML cùng các cách gửi email hoặc lưu kho; cây kế thừa tạo lớp cho từng cặp định dạng–đích gửi và ngày càng khó mở rộng khi thêm kênh mới.
Một service quản lý tài liệu dùng lớp CachedDocumentRepository kế thừa SqlDocumentRepository để bổ sung cache; khi đổi sang kho NoSQL, toàn bộ chức năng cache vẫn gắn với cách lưu SQL cũ.
Nhóm phát triển NotificationServiceWithRetry kế thừa NotificationServiceWithLogging, rồi tạo thêm lớp con mã hóa; đối tác yêu cầu chỉ bật retry không ghi log nội dung, nhưng không có biến thể tương ứng trong cây lớp.
Trong hệ thống ghi nhận hoạt động, một wrapper kiểm toán chuyển lời gọi sang service bên trong nhưng tự xử lý lỗi rồi trả thành công; người dùng nhìn thấy trạng thái hoàn tất dù service gốc đã thất bại.
Đội cần gắn đo thời gian và chính sách retry cho API gọi đối tác; thứ tự hai lớp Decorator làm số lần gọi ghi nhận và thời gian đo khác nhau, khiến số liệu giám sát không khớp kỳ vọng.
Ứng dụng web có các giao diện DarkButton, DarkDialog, LightButton và LightDialog cùng các thư viện render khác nhau; mỗi khi cập nhật renderer, nhiều nhánh kế thừa dành cho theme cũng cần sửa.
Trong công cụ đồ họa, Circle và Rectangle có thể được vẽ bằng raster hoặc vector; các lớp CircleRaster và CircleVector sao chép cả xử lý hình học lẫn cách vẽ, nên thêm một renderer mới làm nhiều lớp phải thay đổi.
Nhóm thiết kế một class base chứa phương thức lưu trữ protected để các subclass tái sử dụng; việc đổi schema dữ liệu buộc mọi lớp con xem lại cách gọi phương thức nội bộ.
Một thư viện Java gọi phương thức có thể override từ constructor của lớp cha; lớp con sử dụng field chưa được khởi tạo và chỉ lỗi khi cấu hình kết nối đặc biệt được chọn.
Ứng dụng ngân hàng tạo BaseTransfer với bước kiểm tra quyền rồi cho các loại chuyển khoản kế thừa; một lớp con ghi đè phương thức thực hiện mà không gọi kiểm tra quyền của lớp cha.
Trong hệ thống đặt vé, FastBooking kế thừa Booking nhưng từ chối thao tác hủy được công bố trong hợp đồng Booking; chức năng xử lý danh sách booking thất bại khi gặp loại nhanh.
Đội tạo AbstractFileProcessor với hàng chục hook cho mọi định dạng; các lớp con chỉ hỗ trợ vài hook và ném lỗi cho phần còn lại, dù các thao tác đó vẫn xuất hiện trong API chung.
Ứng dụng xuất báo cáo dùng lớp con để thêm watermark; đối tượng được cấp quyền mở báo cáo sau khi tạo, nhưng lớp con chỉ gắn watermark ở thời điểm dựng instance và không phản ánh thay đổi quyền.
Một bộ lọc nội dung cho phép chuyển chính sách kiểm duyệt theo thị trường ngay lúc chạy; implementation kế thừa thuật toán mặc định nên ứng dụng phải tạo mới toàn bộ bộ lọc để đổi chính sách.
Nhóm quản lý tồn kho muốn kiểm thử quyết định phân bổ hàng bằng bộ nhớ giả; lớp AllocationService hiện kế thừa trực tiếp JdbcRepository nên kiểm thử thuật toán buộc phải kết nối database thật.
Trong công cụ tìm đường, lớp BaseRoutePlanner giữ cache và cách tính chi phí; nhóm muốn thử nhiều thuật toán tối ưu trên cùng cache nhưng mỗi subclass lại khởi tạo và lưu trạng thái riêng.
Một hệ thống xuất hóa đơn dùng lớp con để thêm chữ ký điện tử; khi chuyển sang nhiều nhà cung cấp chữ ký, mỗi loại hóa đơn phải có subclass riêng cho từng nhà cung cấp.
Đội phát triển dùng một lớp con để bổ sung tính năng nén khi lưu file; thao tác đọc trong lớp cha không biết dữ liệu đã nén, nên cùng đối tượng ghi thành công nhưng không đọc lại được.
Trong phần mềm CRM, CustomerNotification vừa phải gửi email vừa ghi lịch sử; nhóm kế thừa EmailSender để sử dụng phương thức gửi, khiến mọi thay đổi ở EmailSender ảnh hưởng cả lưu nhật ký CRM.
Ứng dụng mô phỏng trò chơi cho phép nhân vật học kỹ năng mới trong trận; lớp nhân vật được xác định bằng hệ phân cấp Fighter, Healer và Mage nên tổ hợp kỹ năng phát sinh không phù hợp với kiểu lớp đã tạo.
Nhóm dùng subclass để biểu diễn cách xác thực mật khẩu theo từng chuẩn; khi người dùng đổi từ mật khẩu truyền thống sang xác thực một lần, controller phải thay cả đối tượng tài khoản chứa dữ liệu hồ sơ.
Trong hệ thống thống kê, một Decorator ghi kết quả vào cache còn Decorator khác thay đổi chính sách làm tròn; cùng dữ liệu có thể nhận kết quả khác nhau tùy thứ tự bọc hai thành phần.
Đội dùng nhiều wrapper lồng nhau để thêm logging, retry và kiểm toán; khi xảy ra exception, stack trace chỉ hiển thị lớp wrapper ngoài cùng nên khó xác định thành phần nghiệp vụ tạo lỗi.
Ứng dụng cho phép truyền các bộ xử lý qua interface nhưng một số đoạn code vẫn ép kiểu sang subclass cụ thể để gọi tính năng phụ; thay đổi sang implementation mới làm lỗi ép kiểu xuất hiện khi chạy.
Trong dự án Java lâu năm, một class base có 25 trường protected được các lớp con sửa trực tiếp; cập nhật quy tắc bất biến của một trường buộc rà soát toàn bộ hệ phân cấp nhiều cấp.
Đội kiểm thử dùng subclass để thay thế dịch vụ thanh toán thật, nhưng mock kế thừa cả phần gửi request mạng; khi phương thức cha được gọi ngầm ở hook mới, bộ test vô tình truy cập API bên ngoài.
Một service giao dịch có các lớp con xử lý Visa và Mastercard; nhà cung cấp mới hỗ trợ đồng thời nhiều phương thức, nhưng logic được viết để mỗi đối tượng chỉ thuộc đúng một subclass.
Nhóm tạo lớp con để thay đổi format ngày trong báo cáo; theo locale của từng request, cùng instance báo cáo cần nhiều format khác nhau nhưng kiểu đối tượng đã cố định từ lúc tạo.
Trong công cụ biên tập nội dung, chức năng kiểm tra chính tả và dịch máy được đặt trong các lớp con của Editor; người dùng muốn bật cả hai nhưng không có lớp nào đáp ứng tổ hợp đó.
Ứng dụng IoT có các thiết bị dùng chung bộ phát lệnh và nhiều giao thức giao tiếp; cây kế thừa theo loại thiết bị khiến cùng một bản vá giao thức phải lặp lại ở tất cả dòng thiết bị.
Nhóm refactor một hệ thống kế thừa sâu sang các thành phần có thể phối hợp; các subclass hiện phụ thuộc vào việc phương thức protected được gọi theo đúng thứ tự ngầm định nên thay đổi cấu trúc dễ làm sai trạng thái.
Một adapter Java nhận đối tượng xử lý được tạo từ cấu hình; thành phần mới không giữ được hợp đồng về timeout giống implementation cũ và làm phần điều phối phụ thuộc vào chi tiết đối tác.
Đội muốn đo khả năng bảo trì sau khi chuyển bớt hành vi từ lớp con sang đối tượng được ủy quyền; hiện mỗi yêu cầu mới vẫn phải sửa nhiều nơi lựa chọn implementation và nhiều test phụ thuộc lớp concrete.
Trong hệ thống đặt hàng, class OrderService kế thừa BaseService chỉ để dùng tiện ích ghi log nhưng cũng nhận các phương thức cập nhật dữ liệu không liên quan; lỗi gọi nhầm phương thức kế thừa làm thay đổi trạng thái đơn.
