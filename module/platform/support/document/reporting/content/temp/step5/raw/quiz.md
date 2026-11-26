JRXML trong JasperReports chủ yếu mô tả điều gì?
A. Dữ liệu của một lần fill đã chạy
B. Bố cục và định nghĩa báo cáo
C. Tệp PDF kết quả cuối cùng
D. Trạng thái connection JDBC đang mở
Đáp án đúng: B

Hai bước compile và fill report khác nhau ở điểm nào?
A. Compile chỉ xuất PDF, fill xuất Excel
B. Compile thiết kế, fill gắn dữ liệu
C. Compile trích dữ liệu, fill ghi JRXML
D. Compile phân trang, fill kiểm tra XML
Đáp án đúng: B

Đối tượng JasperReport thường biểu diễn điều gì?
A. Đối tượng kết nối JDBC trực tiếp
B. Bộ trang kết quả đã chứa dữ liệu
C. Mẫu báo cáo đã được biên dịch
D. Đường dẫn của file PDF vừa xuất
Đáp án đúng: C

JasperPrint thường chứa thông tin nào?
A. Các trang báo cáo sau khi fill
B. Cây biểu thức JRXML chưa biên dịch
C. Danh sách tham số JDBC chưa dùng
D. Cấu hình driver database dự phòng
Đáp án đúng: A

Khi cần truyền bộ lọc từ Java vào báo cáo, thành phần nào phù hợp?
A. Parameter truyền vào lúc fill
B. Static text trong phần page header
C. Field được đọc tự động từ record
D. Variable được cộng dồn theo nhóm
Đáp án đúng: A

Field của JasperReports thường lấy giá trị từ đâu?
A. Định nghĩa style trong JRXML
B. Giá trị tổng cộng của cả báo cáo
C. Giá trị tham số do caller truyền
D. Record hiện tại của nguồn dữ liệu
Đáp án đúng: D

Variable trong báo cáo phù hợp nhất cho việc gì?
A. Tính toán tổng hoặc lũy kế
B. Đặt địa chỉ JDBC của data source
C. Xác định file JRXML cần compile
D. Lưu quyền truy cập file đầu ra
Đáp án đúng: A

Để fill báo cáo từ dữ liệu Java List, có thể dùng gì?
A. JasperPrint làm nguồn record đầu vào
B. JRBeanCollectionDataSource phù hợp
C. JRExporter thay cho mọi datasource
D. JRStyle giữ collection nghiệp vụ
Đáp án đúng: B

Khi dùng JDBC làm nguồn dữ liệu, điểm nào cần quản lý?
A. Tên class của file JRXML
B. Số trang của bản PDF kết quả
C. Connection và vòng đời truy vấn
D. Tên sheet sau khi xuất Excel
Đáp án đúng: C

Tham số trong truy vấn Jasper nên được xử lý thế nào?
A. Nhúng nguyên mật khẩu vào JRXML
B. Đưa giá trị vào font style của cột
C. Ghép mọi giá trị vào chuỗi SQL thô
D. Bind tham số vào truy vấn SQL
Đáp án đúng: D

Biểu thức field trong JRXML cần phù hợp điều gì?
A. Kiểu Java và phạm vi biểu thức
B. Tên class luôn phải là String
C. Mọi giá trị chỉ được xuất vào PDF
D. Giá trị dữ liệu luôn là số nguyên
Đáp án đúng: A

Khi biểu thức gặp null, cách thiết kế an toàn là gì?
A. Kiểm tra null trước khi render
B. Ép toàn bộ field thành primitive
C. Bỏ mọi record chứa giá trị null
D. Tự động chuyển null thành số một
Đáp án đúng: A

Group trong JasperReports được định nghĩa theo gì?
A. Số dòng JRXML của report
B. Biểu thức khóa nhóm từ record
C. Tên của file export PDF đích
D. Vị trí của font trong classpath
Đáp án đúng: B

Group header và footer thường phục vụ gì?
A. Thiết lập chứng thư ký số PDF
B. Khởi tạo JDBC và dọn connection
C. Tiêu đề và tổng kết theo nhóm
D. Đổi kiểu file đầu ra giữa trang
Đáp án đúng: C

Detail band được lặp lại theo yếu tố nào?
A. Số parameter được khai báo
B. Số lần report được biên dịch
C. Mỗi record của data source
D. Số font được nhúng vào trang
Đáp án đúng: C

Page header khác title band ở đặc điểm nào?
A. Title lặp lại theo từng record dữ liệu
B. Title tự động cộng dồn biến nhóm
C. Page header chỉ hiện sau summary
D. Page header được lặp theo trang
Đáp án đúng: D

Summary band thường phù hợp với nội dung nào?
A. Phần chú thích của mỗi field
B. Phần khởi tạo kết nối dữ liệu
C. Phần tiêu đề của từng record
D. Tổng kết của toàn báo cáo
Đáp án đúng: D

printWhenExpression ảnh hưởng gì tới phần tử?
A. Thứ tự compile các subreport
B. Điều kiện in của phần tử
C. Kiểu database của một field
D. Tên file xuất PDF hoặc Excel
Đáp án đúng: B

Khi chuỗi text dài hơn vùng ban đầu, cần cân nhắc gì?
A. Đổi connection pool của JDBC
B. Stretch để mở rộng text field
C. Chuyển mọi giá trị thành Boolean
D. Tăng số biến cục bộ trong Java
Đáp án đúng: B

Để tránh nội dung bị cắt qua trang, yếu tố nào quan trọng?
A. Tên folder chứa file JRXML
B. Thứ tự import các class Java
C. Số chữ số của ID trong database
D. Split band và cách ngắt trang
Đáp án đúng: D

Khi report không có bản ghi, cơ chế nào nên kiểm tra?
A. Trình tạo biểu đồ loại bar chart
B. When No Data Type và noData band
C. Hàng tổng của Excel sau export
D. Group footer của record cuối cùng
Đáp án đúng: B

Khi subreport cần nhận dữ liệu riêng, cách nào đúng?
A. Dùng lại mọi field mà không khai báo
B. Đưa mọi record vào biến group hiện tại
C. Truyền data source cho subreport
D. Truyền tên file PDF đã kết xuất
Đáp án đúng: C

Để truyền ngữ cảnh từ report cha xuống subreport, cần gì?
A. Đổi tên nhóm trong report cha
B. Chuyển content stream sang hình ảnh
C. Tăng khoảng cách giữa các band
D. Ánh xạ parameter cho subreport
Đáp án đúng: D

Crosstab thường hữu ích khi cần hiển thị gì?
A. Một dòng tiêu đề static text
B. Một đoạn mô tả dài không cấu trúc
C. Tổng hợp theo hai chiều hàng và cột
D. Danh sách ảnh không có dữ liệu số
Đáp án đúng: C

Khi xây biểu đồ từ dữ liệu báo cáo, cần xác định gì?
A. Dataset và category của chart
B. Độ rộng của vùng footer
C. Mật khẩu JDBC trong series name
D. Tên file JRXML của band summary
Đáp án đúng: A

Style dùng chung trong JasperReports hỗ trợ gì?
A. Thay thế câu truy vấn nguồn dữ liệu
B. Đồng bộ trạng thái kết nối JDBC
C. Thống nhất định dạng các phần tử
D. Lưu kết quả tính tổng của variable
Đáp án đúng: C

Conditional style nên áp dụng theo yếu tố nào?
A. Tên người dùng tải báo cáo về
B. Biểu thức điều kiện của style
C. Số lần service Java khởi động
D. Phiên bản driver JDBC đang cài
Đáp án đúng: B

Để chữ tiếng Việt xuất PDF ổn định, cần kiểm tra gì?
A. Font có glyph và được nhúng
B. Tên file JRXML chứa dấu tiếng Việt
C. Encoding mặc định của database
D. Số lượng record trong report
Đáp án đúng: A

Khi cấu hình font PDF trong JasperReports, rủi ro nào đáng chú ý?
A. Mỗi band buộc dùng một tên font khác
B. Thêm một image luôn thay font đang dùng
C. Fallback font không nhất quán
D. Mọi font Unicode có độ rộng như nhau
Đáp án đúng: C

Để định dạng số hoặc ngày theo ngôn ngữ, yếu tố nào hữu ích?
A. Tên folder chứa thư viện Jasper
B. Locale và pattern định dạng
C. Số dòng chi tiết trong JRXML
D. Số luồng trong hệ thống export
Đáp án đúng: B

Khi dùng timezone trong báo cáo, nên quan tâm gì?
A. Kích thước ảnh dùng trong header
B. Định danh group đã khai báo
C. Số record được lấy trong JDBC
D. Múi giờ diễn giải dữ liệu
Đáp án đúng: D

Khi export báo cáo sang XLSX, điều gì cần lưu ý?
A. Mỗi trang PDF luôn thành một workbook
B. Workbook không có kiểu dữ liệu số
C. Kiểu dữ liệu ô và bố cục XLSX
D. Mọi field luôn bị đổi thành hình ảnh
Đáp án đúng: C

Vì sao bảng Excel xuất từ report có nhiều ô gộp?
A. Tọa độ thiết kế ánh xạ vào lưới Excel
B. SQL luôn trả dữ liệu đã gộp sẵn
C. Font unicode không tương thích Excel
D. JRXML tự định nghĩa merged cells JDBC
Đáp án đúng: A

Với PDF đầu ra, đặc điểm nào cần test?
A. Tốc độ nhập công thức vào Excel
B. Độ rộng cột trên spreadsheet gốc
C. Tên sheet do người dùng đặt trước
D. Phân trang và tọa độ hiển thị
Đáp án đúng: D

Khi xuất CSV, hạn chế chính so với PDF là gì?
A. CSV không có bố cục trang
B. Không thể xuất nhiều dòng dữ liệu
C. Không thể chứa giá trị dữ liệu text
D. Không thể chứa dấu phân cách trường
Đáp án đúng: A

Khi sửa JRXML, cách phát hiện lỗi sớm phù hợp là gì?
A. Xem thời điểm chỉnh sửa file
B. Đợi người dùng mở bản PDF đầu tiên
C. Kiểm tra file có extension .jrxml
D. Validate JRXML tại bước build
Đáp án đúng: D

Để giảm thời gian tạo nhiều báo cáo cùng mẫu, nên làm gì?
A. Lưu JasperPrint dùng chung mọi request
B. Cache JasperReport đã compile hợp lệ
C. Compile lại JRXML cho từng record
D. Tạo connection mới cho từng field
Đáp án đúng: B

Khi báo cáo có dữ liệu rất lớn, hướng xử lý nào hữu ích?
A. Đọc toàn bộ bảng bất kể bộ lọc
B. Giảm dữ liệu và bật virtualizer
C. Tạo một JRXML mới cho từng trang
D. Giữ mọi JasperPrint mãi trong RAM
Đáp án đúng: B

Vai trò của virtualizer trong JasperReports là gì?
A. Chuyển file XLSX trở lại thành JRXML
B. Giải mã mật khẩu của JDBC connection
C. Giảm áp lực bộ nhớ khi fill nhiều trang
D. Thay thế toàn bộ cơ chế group expression
Đáp án đúng: C

Với truy vấn báo cáo nặng, tối ưu nào nên cân nhắc?
A. Thêm nhiều subreport dùng cùng full scan
B. Tăng chiều cao title band ở JRXML
C. Chuyển mọi column thành static text
D. Lọc, index và giảm dữ liệu từ database
Đáp án đúng: D

Khi report chứa dữ liệu nhiều người dùng, kiểm soát nào quan trọng?
A. Đổi tên report theo từng người
B. Giấu parameter trên giao diện
C. Đổi màu text của record không được xem
D. Lọc dữ liệu theo quyền người xem
Đáp án đúng: D

Để tránh lộ bí mật khi debug report, nên làm gì?
A. Ẩn credential khỏi log debug
B. Dùng mật khẩu làm tên output PDF
C. Đưa connection string vào page header
D. Lưu thông tin JDBC trong log truy cập
Đáp án đúng: A

Nếu tham số đầu vào thiếu hoặc sai, backend nên làm gì?
A. Lặp lại compile cho tới khi hợp lệ
B. Validate parameter trước khi fill
C. Bỏ qua mọi lỗi và export file trống
D. Mặc định nối nó vào SQL truy vấn
Đáp án đúng: B

Khi export nhiều định dạng đầu ra, tổ chức nào hợp lý?
A. Tách fill report khỏi từng exporter
B. Chuyển mỗi format về ảnh trước
C. Viết lại quy tắc nghiệp vụ cho mỗi file
D. Dùng chung một output stream đã đóng
Đáp án đúng: A

Khi báo cáo chạy lâu, cơ chế nào phù hợp hơn?
A. Thử lại liên tục không giới hạn
B. Tăng số lần render cùng một báo cáo
C. Chạy job nền có theo dõi
D. Giữ HTTP request mở vô thời hạn
Đáp án đúng: C

Để đặt tên và lưu file báo cáo, cần cân nhắc gì?
A. Số thứ tự của field trong JRXML
B. Màu background của band detail
C. Tên trình soạn thảo file gốc
D. Phân quyền và vòng đời lưu trữ
Đáp án đúng: D

Khi test JasperReports, cách nào kiểm chứng tốt hơn?
A. Kiểm tra dữ liệu, nhóm và trang
B. Đối chiếu tên và đường dẫn file PDF
C. So sánh kích thước tệp xuất ra
D. Đếm số dòng và số field trong JRXML
Đáp án đúng: A

Để test báo cáo có tổng tiền, fixture nên như thế nào?
A. Tạo danh sách record ngẫu nhiên
B. Lấy dữ liệu production thay đổi theo giờ
C. Dữ liệu biết rõ tổng và giá trị biên
D. Kiểm tra trường text trên header
Đáp án đúng: C

Nếu các format PDF và XLSX có kết quả khác nhau, nên kiểm tra gì?
A. Ngày build của ứng dụng
B. Cách exporter ánh xạ bố cục
C. Số bản ghi trong kết nối JDBC
D. Tên class xử lý người dùng
Đáp án đúng: B

Một lỗi tổng theo nhóm trong JasperReports thường liên quan gì?
A. Khóa nhóm và chu kỳ reset variable
B. Màu nền của style vùng header
C. Tên file được export vào thư mục
D. Số lần thư viện Jasper được tải
Đáp án đúng: A
