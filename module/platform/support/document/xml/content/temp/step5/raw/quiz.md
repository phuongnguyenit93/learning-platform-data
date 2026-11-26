Một tệp XML đóng thẻ đúng nhưng vi phạm kiểu dữ liệu trong XSD được xem là gì?
A. Hợp lệ với XSD vì thẻ đã đóng đúng
B. Chỉ sai namespace, không sai ràng buộc kiểu
C. Không well-formed và cũng không thể parse
D. Well-formed nhưng không hợp lệ với schema
Đáp án đúng: D

Namespace của phần tử XML được xác định chủ yếu nhờ điều gì?
A. Chỉ chuỗi tiền tố trước dấu hai chấm
B. Tên tệp XSD và đường dẫn lưu tài liệu
C. Thứ tự khai báo thuộc tính trong thẻ mở
D. Tên cục bộ kết hợp namespace URI
Đáp án đúng: D

Với default namespace trong XML, nhận định nào đúng về thuộc tính không tiền tố?
A. Thuộc tính không tiền tố tự nhận URI của XSD
B. Thuộc tính không tiền tố luôn thuộc default namespace
C. Thuộc tính không tiền tố không tự nhận default namespace
D. Mọi thuộc tính dùng namespace của phần tử cha
Đáp án đúng: C

Một XSD khai báo phần tử `price` có kiểu decimal; việc validation phát hiện gì?
A. Đơn vị tiền tệ sai quy tắc của toàn hệ thống
B. Thứ tự lời gọi Java khi đọc phần tử `price`
C. Mọi giá trị âm đều sai ngay cả khi schema cho phép
D. Giá trị không phù hợp kiểu decimal đã khai báo
Đáp án đúng: D

Khi chọn DOM để sửa một vài node của tài liệu XML nhỏ, lợi điểm chính là gì?
A. Có cây trong bộ nhớ để truy cập và chỉnh node
B. Đọc theo event callback mà không giữ cây XML
C. Tiêu thụ bộ nhớ gần như không phụ thuộc độ lớn
D. Chỉ đọc một chiều, không thể trở về node trước
Đáp án đúng: A

Đọc tệp XML rất lớn chỉ để đếm thẻ, đặc điểm nào khiến SAX phù hợp?
A. Có thể đọc ngược sự kiện bất cứ lúc nào
B. Nạp toàn bộ document thành node tree để truy cập
C. Xử lý tuần tự bằng callback, không giữ toàn bộ cây
D. Tự chuyển schema thành các Java class cố định
Đáp án đúng: C

StAX khác SAX chủ yếu ở cách điều khiển luồng đọc như thế nào?
A. Ứng dụng chủ động kéo sự kiện từ XML reader
B. Parser luôn tạo sẵn toàn bộ cây trước khi đọc
C. Ứng dụng bắt buộc dùng XPath trên mỗi event
D. Parser luôn đẩy event qua callback đăng ký trước
Đáp án đúng: A

Trong Java, JAXB thường được dùng cho việc nào?
A. Biến đổi XML thành HTML bằng stylesheet XSLT
B. Ánh xạ XML với object Java khi marshal/unmarshal
C. Đếm thẻ bằng callback streaming SAX handler
D. Dò các lỗ hổng XXE qua kết nối HTTP ngoài
Đáp án đúng: B

XPath tìm phần tử có namespace nhưng query dùng tên không tiền tố trả trống; cách sửa nào phù hợp?
A. Chỉ đổi đường dẫn XPath sang tên file XML
B. Bind prefix vào namespace URI rồi dùng trong XPath
C. Đổi toàn bộ ký tự tên phần tử thành chữ hoa
D. Bỏ thuộc tính namespace khỏi tài liệu trước mỗi lần tìm
Đáp án đúng: B

XSLT có vai trò phù hợp nào trong luồng xử lý tài liệu XML?
A. Chuyển XML thành cấu trúc khác bằng stylesheet
B. Đọc XML theo pull event qua StAX reader
C. Chỉ kiểm ràng buộc kiểu và thứ tự của XSD
D. Khóa mọi entity ngoài chỉ bằng thay tên namespace
Đáp án đúng: A

Khi đọc XML không đáng tin, bước phòng chống XXE quan trọng là gì?
A. Cho phép tải entity từ mọi địa chỉ ngoài internet
B. Chặn entity ngoài và DTD không cần thiết
C. Bật resolve entity trước để phát hiện lỗi sớm
D. Chỉ kiểm extension `.xml` trước khi parse dữ liệu
Đáp án đúng: B

Vì sao chỉ xác thực XSD chưa đủ để loại nguy cơ XXE?
A. XML parser có thể xử lý entity ngoài trước validation
B. Dùng XSD làm mọi XML parser trở nên bất biến
C. Schema luôn tự vô hiệu mọi lời gọi tới mạng nội bộ
D. XSD chỉ kiểm tra tên tệp, không đọc nội dung XML
Đáp án đúng: A

Tài liệu XML không đóng đúng thẻ; công đoạn nào phát hiện lỗi này đầu tiên?
A. Chỉ bước biến đổi XSLT sau khi stylesheet hoàn tất
B. Chỉ ứng dụng gọi XPath đến phần tử cuối cùng
C. Chỉ bước mapping JAXB sau khi object đã tạo
D. Phân tích cú pháp well-formedness trước validation
Đáp án đúng: D

Đưa trực tiếp đầu vào người dùng vào biểu thức XPath gây nguy cơ nào?
A. Chuyển nội dung XML sang charset khác ngoài ý muốn
B. Tự đổi namespace URI của toàn bộ tài liệu đã parse
C. Làm thay đổi ý nghĩa truy vấn qua XPath injection
D. Làm XSD tự thêm phần tử vào XML gốc khi kiểm tra
Đáp án đúng: C

Khi cần phân tích streaming mà vẫn tự quyết định lúc lấy sự kiện tiếp theo, chọn API nào?
A. XSLT với stylesheet biến đổi cấu trúc
B. Dùng StAX để kéo sự kiện theo nhu cầu
C. DOM với cây Document nạp hoàn chỉnh
D. JAXB với đối tượng đã unmarshall toàn bộ
Đáp án đúng: B

Khi ghi XML chứa chuỗi `A&B` vào text node, phải xử lý thế nào?
A. Thay dấu `&` bằng namespace URI của element
B. Bọc toàn bộ dữ liệu vào thẻ `xsd:string`
C. Escape dấu `&` thành `&amp;` khi serialize
D. Giữ dấu `&` thô vì chỉ thuộc tính mới cần escape
Đáp án đúng: C
