Bạn xác định những dấu hiệu nào cho thấy một miền nghiệp vụ nên có Domain-Specific Language thay vì tiếp tục dùng mã ứng dụng thông thường?
Bạn phân biệt DSL với ngôn ngữ lập trình đa dụng, tệp cấu hình và API thư viện bằng những đặc điểm nào?
Bạn thu thập thuật ngữ và quy tắc từ chuyên gia nghiệp vụ để xác định từ vựng cốt lõi của một DSL như thế nào?
Bạn xác định ranh giới trách nhiệm của DSL để tránh biến nó thành một ngôn ngữ lập trình đa dụng khó kiểm soát ra sao?
Bạn đánh giá ai sẽ là người đọc, viết và duyệt DSL để định hướng thiết kế cú pháp như thế nào?
Bạn lựa chọn internal DSL hay external DSL dựa trên khả năng diễn đạt, chi phí triển khai và trải nghiệm người dùng ra sao?
Bạn giải thích cách internal DSL tận dụng cú pháp và hệ thống kiểu của ngôn ngữ chủ như thế nào?
Nếu cú pháp của ngôn ngữ chủ làm câu lệnh nghiệp vụ trở nên khó hiểu, bạn điều chỉnh thiết kế internal DSL ra sao?
Bạn lựa chọn biểu diễn DSL bằng văn bản, cấu trúc dữ liệu hay giao diện trực quan cho từng nhóm người dùng như thế nào?
Bạn chuyển một quy tắc nghiệp vụ diễn đạt bằng ngôn ngữ tự nhiên thành ví dụ DSL có thể kiểm chứng như thế nào?
Bạn thiết kế tên lệnh, từ khóa và cấu trúc biểu thức để người dùng không phải học nhiều chi tiết kỹ thuật ra sao?
Bạn xác định những khái niệm nào nên được biểu diễn thành khai báo và những khái niệm nào cần hỗ trợ thao tác có thứ tự như thế nào?
Bạn thiết kế cú pháp điều kiện, toán tử và dấu nhóm để loại bỏ cách hiểu mơ hồ như thế nào?
Bạn lựa chọn mức độ ngắn gọn của cú pháp so với tính tường minh để giảm lỗi khi người dùng viết quy tắc ra sao?
Bạn mô tả vai trò của lexer, parser, phân tích ngữ nghĩa và thực thi trong pipeline xử lý external DSL như thế nào?
Bạn thiết kế token và xử lý khoảng trắng, chuỗi ký tự, số, comment trong một DSL văn bản như thế nào?
Bạn biểu diễn ngữ pháp cho một tập quy tắc có điều kiện lồng nhau và phát hiện trường hợp mơ hồ ra sao?
Bạn lựa chọn phương pháp phân tích cú pháp dựa trên độ phức tạp ngữ pháp và yêu cầu thông báo lỗi như thế nào?
Khi người dùng nhập cú pháp chưa hoàn chỉnh, bạn thiết kế thông báo lỗi chỉ rõ vị trí và cách sửa như thế nào?
Bạn phân biệt concrete syntax tree và abstract syntax tree về thông tin cần lưu giữ cho các công cụ như thế nào?
Bạn thiết kế các node AST để biểu diễn điều kiện, hành động và biểu thức mà không phụ thuộc quá chặt vào cú pháp văn bản ra sao?
Bạn lưu vị trí nguồn và ngữ cảnh trên AST để phục vụ chẩn đoán lỗi hoặc đánh dấu trong editor như thế nào?
Bạn thiết kế bảng ký hiệu và phạm vi tên khi DSL cho phép khai báo biến hoặc tham chiếu thực thể nghiệp vụ ra sao?
Bạn xác định các quy tắc kiểm tra kiểu và tính hợp lệ của biểu thức trước khi thực thi DSL như thế nào?
Khi một quy tắc dùng trường dữ liệu không tồn tại trong mô hình nghiệp vụ, bạn phát hiện và giải thích lỗi ở giai đoạn nào?
Bạn xử lý các quy tắc mâu thuẫn, chồng lấn hoặc thiếu trường hợp trong cùng một tập DSL như thế nào?
Bạn thiết kế giá trị mặc định và quy tắc ưu tiên để kết quả DSL không phụ thuộc vào những giả định ngầm ra sao?
Bạn tổ chức các bước chuyển đổi và chuẩn hóa AST trước khi chạy chương trình như thế nào?
Bạn lựa chọn interpreter hay code generator cho DSL dựa trên tốc độ chạy, tính linh hoạt và chi phí bảo trì ra sao?
Bạn thiết kế một interpreter duyệt AST và truyền context đánh giá các biểu thức như thế nào?
Khi DSL sinh mã nguồn của ngôn ngữ khác, bạn bảo đảm mã sinh ra giữ đúng ý nghĩa của quy tắc ban đầu ra sao?
Bạn kiểm soát thứ tự đánh giá và các tác dụng phụ để cùng một đầu vào luôn cho kết quả có thể dự đoán như thế nào?
Bạn thiết kế cơ chế báo lỗi khi thực thi DSL để người dùng truy được quy tắc và dữ liệu gây lỗi ra sao?
Khi một quy tắc được gọi lặp lại hoặc tạo chuỗi phụ thuộc vòng, bạn phát hiện và ngăn thực thi vô hạn như thế nào?
Bạn xác định mô hình phân quyền cho người viết, người phê duyệt và người thực thi DSL như thế nào?
Bạn ngăn người dùng lợi dụng DSL để thực thi mã tùy ý hoặc truy cập tài nguyên ngoài phạm vi cho phép ra sao?
Bạn thiết kế sandbox và giới hạn thời gian, bộ nhớ, số bước thực thi cho DSL nhận đầu vào không tin cậy như thế nào?
Khi DSL cho phép chèn dữ liệu vào truy vấn hoặc lệnh hệ thống, bạn phòng chống injection bằng thiết kế nào?
Bạn xử lý dữ liệu bí mật và thông tin nhạy cảm trong log, lỗi và kết quả thực thi DSL như thế nào?
Bạn xây dựng bộ kiểm thử parser để bao phủ cú pháp hợp lệ, cú pháp sai và các trường hợp biên như thế nào?
Bạn kiểm chứng rằng AST và interpreter thực hiện đúng các ví dụ do chuyên gia nghiệp vụ cung cấp như thế nào?
Bạn sử dụng property-based testing hoặc fuzzing để phát hiện lỗi phân tích cú pháp và thực thi DSL ra sao?
Bạn thiết kế kiểm thử hồi quy khi thay đổi ngữ pháp hoặc quy tắc đánh giá để tránh làm sai kịch bản cũ như thế nào?
Bạn tạo công cụ gợi ý cú pháp, kiểm tra lỗi và hoàn thành từ khóa trong IDE hoặc editor của DSL như thế nào?
Bạn tổ chức trace hoặc cơ chế giải thích kết quả để người dùng biết vì sao một tập quy tắc đưa ra quyết định nào đó ra sao?
Bạn thiết kế phiên bản ngôn ngữ và chính sách tương thích ngược khi cần mở rộng từ khóa hay biểu thức như thế nào?
Bạn lập kế hoạch chuyển đổi các quy tắc DSL đã lưu khi thay đổi ngữ pháp hoặc ngữ nghĩa như thế nào?
Bạn xây dựng cơ chế mở rộng DSL bằng hàm hoặc module mới mà vẫn bảo vệ bất biến và bảo mật hệ thống ra sao?
Bạn so sánh khả năng tái sử dụng, kết hợp và kiểm thử khi tách một DSL lớn thành các quy tắc hoặc module nhỏ như thế nào?
Khi một thay đổi DSL ảnh hưởng đến nhiều bộ phận nghiệp vụ, bạn thiết kế quy trình review, thử nghiệm và rollback ra sao?
Bạn đo hiệu năng của quá trình parse và thực thi DSL, rồi quyết định có nên cache AST hay mã đã biên dịch như thế nào?
