Trong Apache POI, interface nào biểu diễn toàn bộ workbook bất kể định dạng Excel cụ thể?
A. Sheet cung cấp thao tác chung cho toàn bộ tệp và phần metadata
B. Row cung cấp thao tác chung cho tất cả bảng tính của workbook
C. Workbook là interface quản lý các sheet và dữ liệu của một tệp
D. CellStyle cung cấp thao tác chung cho mọi workbook được mở
Đáp án đúng: C

Khi cần đọc cả .xls và .xlsx, cách tiếp cận nào giảm mã phụ thuộc định dạng?
A. Dùng riêng XSSFWorkbook cho mọi tệp rồi đổi phần mở rộng khi cần
B. Dùng HSSFWorkbook cho mọi tệp vì định dạng đọc được tự động nhận diện
C. Đọc các byte đầu thành chuỗi CSV rồi dựng lại các sheet tương ứng
D. Dùng WorkbookFactory để mở tệp rồi thao tác qua interface Workbook
Đáp án đúng: D

Khi tạo workbook Excel theo định dạng .xls cũ, lớp nào phù hợp hơn?
A. HSSFWorkbook tạo workbook theo định dạng nhị phân .xls cũ
B. XSSFWorkbook cung cấp cấu trúc workbook Open XML có tệp .xlsx
C. SXSSFWorkbook cung cấp workbook để streaming nội dung .xls cũ
D. XSSFReader cung cấp API tạo và ghi workbook ở định dạng .xls
Đáp án đúng: A

Với workbook .xlsx thông thường cần sửa nhiều ô trong bộ nhớ, nên chọn gì?
A. XSSFWorkbook hỗ trợ mô hình tài liệu Open XML có thể chỉnh sửa
B. HSSFWorkbook hỗ trợ mọi tệp Open XML không cần chuyển đổi định dạng
C. SXSSFWorkbook luôn đọc các sheet hiện hữu và sửa tùy ý mọi dòng cũ
D. XSSFReader tự tạo các ô mới và giữ toàn bộ model trong bộ nhớ
Đáp án đúng: A

Khi truy cập một sheet theo tên, cần xử lý tình huống nào?
A. Workbook luôn tự tạo sheet nếu tên chưa tồn tại trong tệp nguồn
B. Sheet có thể không tồn tại, cần kiểm tra trước khi duyệt các hàng
C. API sẽ mặc định trả về sheet đầu tiên khi tên nhập không tìm thấy
D. Tên sheet được đối chiếu theo vị trí thay vì nội dung chuỗi đầu vào
Đáp án đúng: B

Vì sao cần chú ý chỉ số khi lấy Row và Cell bằng POI?
A. POI luôn đánh số hàng từ 1, còn các cột tính từ chữ A bắt đầu ở 1
B. Hàng dùng chỉ số ký tự, còn cột là số âm tùy theo workbook đang đọc
C. Vị trí hàng, cột tự hiệu chỉnh theo ô đầu tiên đang có dữ liệu
D. Các chỉ số hàng và cột của POI đều bắt đầu từ số 0
Đáp án đúng: D

Khi một hàng có ô trống ở giữa, cách duyệt nào tránh lệch cột?
A. Dựa vào vị trí cột và chính sách đối với ô còn thiếu
B. Dồn toàn bộ ô đang có sang trái trước khi ánh xạ dữ liệu vào đối tượng
C. Đọc header rồi giả định mọi cột tiếp theo luôn liền nhau trong hàng
D. Đánh số lại cột theo thứ tự iterator trả về rồi dùng như chỉ số gốc
Đáp án đúng: A

Trong Apache POI, dữ liệu ô dạng công thức được phân loại như thế nào?
A. CellType.NUMERIC luôn cho biết ô đang chứa một công thức tính toán
B. CellType.FORMULA cho biết nội dung ô là biểu thức cần đánh giá
C. CellType.STRING bắt buộc được dùng cho mọi công thức có kết quả chữ
D. CellType.ERROR được dùng cho mọi công thức chưa được cập nhật kết quả
Đáp án đúng: B

Khi một ô hiển thị ngày tháng trong Excel, dữ liệu bên dưới thường là gì?
A. Một chuỗi ISO bắt buộc được lưu trong mọi ô ngày của file .xlsx
B. Ô kiểu số có style ngày, không phải đối tượng Date riêng
C. Đối tượng Date Java được nhúng trực tiếp vào vùng dữ liệu của ô
D. Một công thức bắt buộc tạo ra timestamp ở dạng chuỗi văn bản
Đáp án đúng: B

Nếu cột mã khách hàng có giá trị 00125, nên đọc và lưu theo cách nào?
A. Ép sang số nguyên vì Excel tự giữ số 0 trong giá trị tính toán
B. Làm tròn kiểu double vì mã khách hàng là dữ liệu số thông thường
C. Chuyển thành ngày vì dữ liệu bắt đầu bằng ký tự 0 trong bảng tính
D. Giữ dạng định danh chuỗi để không làm mất các số 0 ở đầu
Đáp án đúng: D

Mục đích của DataFormatter trong Apache POI là gì?
A. Tạo chuỗi theo cách ô được định dạng khi hiển thị trong Excel
B. Ghi công thức mới vào ô và đánh giá mọi hàm của Excel khi lưu tệp
C. Tự thay đổi mọi ô số thành kiểu dữ liệu String trong workbook
D. Tự sửa lỗi định dạng trong mọi sheet và thay đổi giá trị gốc
Đáp án đúng: A

Khi muốn lấy kết quả tính toán hiện tại từ ô công thức, dùng gì?
A. DataFormatter tự tính mọi công thức độc lập với evaluator và workbook
B. FormulaEvaluator tính hoặc lấy kết quả theo khả năng hỗ trợ của POI
C. CellStyle tự tạo giá trị công thức khi đọc kiểu chữ của từng ô
D. Sheet tự chuyển công thức thành hằng số mỗi khi duyệt qua Row
Đáp án đúng: B

Vì sao không nên coi giá trị cached của công thức luôn mới nhất?
A. Giá trị cached chỉ tồn tại với ô văn bản và không liên quan công thức
B. Cache có thể chưa phản ánh các thay đổi ở những ô tham chiếu gần đây
C. POI tự chạy mọi macro trong tệp mỗi lần truy cập cache công thức
D. Excel luôn xóa cache khi lưu nên không thể có giá trị để đọc
Đáp án đúng: B

Khi POI không hỗ trợ một hàm trong công thức Excel, ứng dụng nên làm gì?
A. Chuyển tự động công thức thành chuỗi rỗng để tránh báo lỗi dữ liệu
B. Tự gán kết quả 0 cho công thức rồi xuất báo cáo như bình thường
C. Giữ công thức và xử lý giới hạn đánh giá khi gặp hàm chưa hỗ trợ
D. Đổi ô sang General để thử tính lại khi gặp hàm chưa được hỗ trợ
Đáp án đúng: C

Đối với dữ liệu tiền tệ cần độ chính xác cao, rủi ro nào quan trọng?
A. Ô số được Excel lưu dưới dạng thập phân chính xác theo mọi chữ số
B. Excel dùng số floating-point, cần chính sách làm tròn tiền tệ
C. Định dạng tiền tệ chuyển giá trị thành chuỗi nhằm tránh sai số
D. Phép tính với ô NUMERIC luôn giữ được mọi chữ số thập phân đầu vào
Đáp án đúng: B

Khi gặp một ô có kiểu BOOLEAN, đọc đúng nghĩa là gì?
A. Đọc thành số nguyên vì hai giá trị logic luôn là kiểu NUMERIC
B. Lấy giá trị logic true hoặc false thay vì ép thành chuỗi hiển thị
C. Đọc thành công thức vì trạng thái đúng sai đều do biểu thức tạo ra
D. Đọc thành văn bản bất kỳ và coi mọi chuỗi khác rỗng đều là true
Đáp án đúng: B

Khi một ô không tồn tại khác với ô kiểu BLANK, điều gì cần cân nhắc?
A. Giả định POI tự tạo đối tượng Cell cho mọi vị trí chưa từng ghi
B. Giả định ô không có giá trị luôn được Excel lưu dưới kiểu ERROR
C. Phân biệt ô vắng mặt với ô BLANK qua chính sách đọc
D. Thay hàng thiếu bằng một sheet mới trước khi xác thực dữ liệu
Đáp án đúng: C

Khi chuyển số ngày Excel sang thời gian Java, cần xét điều gì?
A. Số thứ tự hàng và độ rộng cột quyết định trực tiếp múi giờ
B. Tên sheet và màu nền ô quyết định năm tháng của giá trị ngày
C. Số lượng công thức trong tệp quyết định định dạng thời gian
D. Cân nhắc hệ ngày workbook và cách diễn giải vùng giờ
Đáp án đúng: D

Khi muốn hiển thị ngày theo định dạng riêng, POI dùng tổ hợp nào?
A. Dùng CellStyle và DataFormat để đặt cách hiển thị ngày
B. Một Sheet khác lưu tên tháng rồi tham chiếu bằng màu của ô
C. Một HSSFWorkbook lồng trong tệp để giữ định dạng theo vùng giờ
D. Một đối tượng FormulaEvaluator chuyên cập nhật font ngày tháng
Đáp án đúng: A

Khi nhiều ô dùng cùng kiểu định dạng, cách nào tiết kiệm tài nguyên?
A. Tạo một CellStyle mới cho mỗi ô dù mọi thuộc tính đều giống nhau
B. Sao chép toàn bộ workbook cho mỗi hàng cần định dạng lại
C. Chuyển mọi giá trị thành String để không còn cần style nữa
D. Tái sử dụng CellStyle khi các ô có cùng quy tắc định dạng
Đáp án đúng: D

Vì sao số lượng CellStyle cần được quản lý khi xuất báo cáo lớn?
A. Style dùng chung có giới hạn số lượng và tiêu tốn tài nguyên
B. Mỗi kiểu ô buộc phải có một workbook riêng trước khi kết xuất
C. Số lượng style luôn bằng số sheet và không thể tăng theo ô
D. Style không được lưu trong tệp Excel nên chỉ ảnh hưởng ứng dụng
Đáp án đúng: A

Khi đặt chiều rộng cột theo nội dung, cần thận trọng điều gì?
A. Auto-size trên dữ liệu lớn có chi phí và phụ thuộc khả năng đo font
B. Auto-size luôn miễn phí vì không phải đọc các ô để đo nội dung
C. Chiều rộng cột không thể thay đổi sau khi một giá trị được ghi vào ô
D. Tên cột được tự điều chỉnh độ rộng khi mở workbook bằng POI
Đáp án đúng: A

Nếu muốn tô màu ô dựa trên ngưỡng dữ liệu, tính năng nào phù hợp?
A. FormulaEvaluator tự gán màu tùy kết quả khi đánh giá biểu thức
B. WorkbookFactory tự tạo màu theo loại dữ liệu trong từng sheet
C. Sheet iterator áp dụng kiểu màu theo số thứ tự của hàng đọc
D. Conditional formatting tô màu dựa trên quy tắc của ô
Đáp án đúng: D

Khi cần tạo vùng tiêu đề hợp nhất nhiều cột, cần lưu ý điều gì?
A. Merging tự nối mọi giá trị và tự kiểm tra nghiệp vụ trong các cột
B. Một vùng merged buộc phải nằm trên nhiều sheet để hiển thị đúng
C. Hợp nhất ô khiến các công thức tham chiếu tự thay sang bảng mới
D. Merged region phải tránh chồng lấn và bảo đảm phạm vi ô hợp lệ
Đáp án đúng: D

Khi thêm biểu đồ vào báo cáo Excel, điều gì cần liên kết chính xác?
A. Biểu đồ sẽ tự dùng toàn bộ ô bất kể dữ liệu nằm ở sheet nào
B. Biểu đồ mặc định sử dụng vùng đầu tiên có dữ liệu trong workbook
C. Đối chiếu vùng dữ liệu và nhãn trục của biểu đồ với ô nguồn
D. Biểu đồ luôn dùng cột đầu tiên của workbook làm nguồn dữ liệu
Đáp án đúng: C

Khi xuất bảng báo cáo nhiều trang, cách tổ chức nào dễ đọc hơn?
A. Dồn dữ liệu và hướng dẫn vào một ô lớn để giảm số sheet trong tệp
B. Chia sheet theo mục đích, có header và cách định dạng thống nhất
C. Ghi tất cả kết quả thành chuỗi vào ô đầu tiên để bảo đảm nguyên vẹn
D. Dùng một cột chứa JSON thay vì cấu trúc hàng và cột của Excel
Đáp án đúng: B

Khi nhập dữ liệu từ workbook có header thay đổi thứ tự, nên ánh xạ thế nào?
A. Ánh xạ theo cột đầu tiên có độ rộng lớn nhất trong sheet dữ liệu
B. Ánh xạ theo màu nền của từng cột để suy ra tên trường nghiệp vụ
C. Ánh xạ theo tên header đã chuẩn hóa thay vì cố định chỉ số cột
D. Ánh xạ theo thứ tự iterator của các ô không trống ở hàng đầu
Đáp án đúng: C

Khi hai cột có cùng tên header, xử lý nào an toàn hơn?
A. Phát hiện header trùng và yêu cầu xác định cột đúng
B. Gộp dữ liệu hai cột vào cùng một trường mà không cần quy tắc
C. Chọn cột có nhiều ô số nhất dù tên cột trùng nhau trong tệp
D. Giữ cột xuất hiện sau và bỏ qua cột trước mà không ghi cảnh báo
Đáp án đúng: A

Khi import ô số vào trường kiểu int, cần xác thực điều gì?
A. Kích thước font và màu chữ quyết định số có thể chuyển sang int
B. Vị trí của ô trong sheet quyết định giới hạn của kiểu số nguyên
C. Giá trị phải nguyên, hữu hạn và nằm trong phạm vi kiểu int
D. Định dạng phần trăm bảo đảm mọi số là một số nguyên hợp lệ
Đáp án đúng: C

Khi người dùng nhập ngày dưới dạng văn bản, quy trình nào đáng tin cậy?
A. Parse theo định dạng chấp nhận và từ chối ngày mơ hồ
B. Ép mọi chuỗi qua kiểu NUMERIC vì Excel tự đoán ngày chính xác
C. Đọc độ rộng ô rồi chọn vùng giờ thích hợp cho ngày đã nhập
D. Giữ nguyên chuỗi và khẳng định tất cả ngày đều đã được xác thực
Đáp án đúng: A

Khi import một hàng thiếu trường bắt buộc, ứng dụng nên làm gì?
A. Tự xóa toàn bộ workbook vì một hàng thiếu dữ liệu cần thiết
B. Âm thầm dời các giá trị ở cột sau sang trái để lấp ô trống
C. Ghi lỗi theo hàng và cột để người dùng chỉnh dữ liệu
D. Dừng nhập toàn bộ các sheet còn lại khi có một hàng thiếu dữ liệu
Đáp án đúng: C

Khi nhiều hàng chứa dữ liệu trùng mã nghiệp vụ, nên quyết định dựa trên gì?
A. Thứ tự các hàng trên sheet vì mã ở cuối luôn có độ ưu tiên cao
B. Định dạng chữ của ô vì mã màu đậm có nghĩa là bản ghi hợp lệ
C. Theo quy tắc duy nhất nghiệp vụ và cách xử lý dữ liệu trùng
D. Tên sheet vì mã trong sheet đầu không thể trùng với sheet sau
Đáp án đúng: C

Vì sao không nên tin ngay phần mở rộng .xlsx của tệp người dùng tải lên?
A. Cần kiểm tra nội dung, kiểu tệp và giới hạn trước khi xử lý
B. Đuôi .xlsx bảo đảm các byte luôn là Open XML không cần xác thực
C. Tệp có đuôi .xlsx luôn không có công thức hay liên kết ra bên ngoài
D. Tệp có đuôi .xlsx không thể gây tiêu hao tài nguyên khi giải nén
Đáp án đúng: A

Khi đọc workbook .xlsx rất lớn, kỹ thuật nào giảm dùng bộ nhớ?
A. Dùng mô hình đọc sự kiện qua XSSFReader và SAX khi phù hợp luồng
B. Mở nhiều XSSFWorkbook cùng lúc để phân chia số ô giữa các lần đọc
C. Tạo SXSSFWorkbook cho mỗi hàng cần đọc vì đây là reader mặc định
D. Tăng số CellStyle để các sheet tự giải phóng dữ liệu sau khi đọc
Đáp án đúng: A

Cơ chế SXSSFWorkbook phù hợp nhất với tác vụ nào?
A. Đọc ngẫu nhiên mọi hàng của .xls nhị phân mà không dùng bộ nhớ
B. Sửa nội dung của bất kỳ hàng cũ nào sau khi đã flush ra đĩa
C. Ghi .xlsx nhiều hàng theo cửa sổ dòng được giữ trong bộ nhớ
D. Đánh giá mọi công thức nâng cao trong tệp mà không cần evaluator
Đáp án đúng: C

Điều gì xảy ra khi hàng SXSSF đã bị flush khỏi cửa sổ bộ nhớ?
A. Hàng sẽ tự quay lại bộ nhớ khi người dùng gọi getRow lần nữa
B. Dữ liệu hàng đó bị xóa vĩnh viễn khỏi tệp xuất Excel cuối cùng
C. Các công thức trên hàng đã flush được tính thành giá trị trước khi xuất
D. Không còn chỉnh sửa ngẫu nhiên hàng đó qua mô hình dòng hiện tại
Đáp án đúng: D

Khi dùng SXSSFWorkbook, thao tác dọn dẹp nào đặc biệt cần thiết?
A. Giữ toàn bộ tệp tạm trên đĩa để lần đọc tiếp theo nhanh hơn
B. Chuyển mọi tệp tạm thành .xls nhằm tương thích Office cũ
C. Giải phóng tài nguyên và xóa tệp tạm được SXSSF sử dụng
D. Chuyển các dòng công thức thành dữ liệu thường trước khi ghi
Đáp án đúng: C

Khi quyết định đọc bằng DOM-like XSSF hay SAX streaming, cân nhắc gì?
A. Màu nền của workbook và số lượng font đang áp dụng cho các ô
B. Tên file và số ký tự trong metadata của tác giả bảng tính
C. Định dạng cột ngày tháng vì chỉ streaming mới xử lý được ngày
D. Cân nhắc truy cập ngẫu nhiên, kích thước và bộ nhớ sẵn có
Đáp án đúng: D

Với .xls cũ, giới hạn số hàng trên một sheet thường là bao nhiêu?
A. Giới hạn 1.048.576 hàng như mọi định dạng Office Open XML
B. Giới hạn 65.536 hàng trên mỗi sheet của định dạng .xls cũ
C. Giới hạn 16.384 hàng vì đó là số cột của định dạng .xlsx
D. Giới hạn không xác định vì chỉ phụ thuộc bộ nhớ của JVM
Đáp án đúng: B

Khi chuyển một tập dữ liệu lớn sang .xlsx, giới hạn nào cần tính?
A. Giới hạn chỉ số sheet luôn bằng số hàng của định dạng .xls
B. Giới hạn hàng và cột mỗi sheet cùng dung lượng bộ nhớ khi ghi
C. Giới hạn ô số tối đa bằng số lượng CellStyle được khai báo
D. Giới hạn tệp Excel phụ thuộc duy nhất vào tên các sheet tạo ra
Đáp án đúng: B

Khi người dùng nhập nội dung bắt đầu bằng dấu bằng, cần bảo vệ điều gì?
A. Chuyển mọi chuỗi bắt đầu bằng số thành công thức để Excel nhận diện
B. Dùng CellStyle đặt màu cảnh báo để Excel không thực thi biểu thức
C. Tự xóa dấu bằng trong mọi văn bản bất kể ý nghĩa người dùng
D. Giữ dữ liệu không tin cậy là văn bản thay vì công thức Excel
Đáp án đúng: D

Khi xuất báo cáo chứa dữ liệu riêng tư, yêu cầu nào nên áp dụng?
A. Ghi tất cả dữ liệu nguồn vào sheet ẩn và coi như được bảo vệ đầy đủ
B. Giới hạn trường dữ liệu, kiểm soát quyền tải và thời gian lưu tệp
C. Đặt tên file khó đoán thay cho kiểm tra quyền truy cập người dùng
D. Dùng mật khẩu trong tên worksheet để ngăn người khác mở tệp
Đáp án đúng: B

Khi nhận tệp .xlsx nén độc hại, biện pháp nào giảm rủi ro tài nguyên?
A. Đặt giới hạn kích thước và kiểm tra nguy cơ giải nén bất thường
B. Chọn workbook chứa nhiều style vì style giúp giảm dung lượng ZIP
C. Mở toàn bộ tệp trong heap trước khi kiểm tra dung lượng nén
D. Vô hiệu hóa log ứng dụng vì dữ liệu nén không liên quan parser
Đáp án đúng: A

Khi sinh báo cáo nhiều yêu cầu đồng thời, quản lý workbook thế nào?
A. Tạo workbook riêng theo công việc và tránh chia sẻ đối tượng mutable
B. Dùng một XSSFWorkbook chung để nhiều thread ghi vào các sheet khác
C. Đổi tên sheet trong mỗi thread để tránh phải đồng bộ dữ liệu trên RAM
D. Tái sử dụng một output stream cho tất cả yêu cầu đang chờ ghi
Đáp án đúng: A

Khi cần tạo file từ Java/Spring để trả về HTTP, điều gì quan trọng?
A. Ghi tên file vào body HTML thay cho truyền byte của workbook
B. Chuyển workbook thành chuỗi UTF-8 rồi trả về dưới dạng JSON
C. Gửi metadata workbook thay cho dữ liệu để trình duyệt dựng báo cáo
D. Đặt MIME type, tên tệp và stream workbook trong response
Đáp án đúng: D

Cách kiểm thử file Excel xuất ra nào mạnh hơn việc kiểm tra tệp tồn tại?
A. Kiểm tra tệp có đuôi .xlsx mà không cần đọc nội dung được ghi
B. So sánh dung lượng tệp với bản mẫu mà không đối chiếu ô dữ liệu
C. Mở lại workbook rồi kiểm tra giá trị, công thức và style
D. Dựa vào HTTP 200 để kết luận mọi công thức đều chính xác
Đáp án đúng: C

Khi kiểm thử xuất báo cáo bằng SXSSF, nên kiểm tra thêm điều gì?
A. Độ sáng màu nền của Excel có giống chính xác giữa các máy
B. Hàng đã flush có thể gọi lại getRow để thay đổi sau khi kết xuất
C. Kiểm tra nội dung sau ghi và dọn tệp tạm của SXSSF
D. Số lần trình duyệt tải tệp dù bài kiểm thử chỉ chạy server
Đáp án đúng: C

Vì sao dùng DataFormatter thay vì đọc getNumericCellValue cho mọi cột?
A. Cell số trong POI luôn là chuỗi nên getNumericCellValue không tồn tại
B. Hiển thị số 0 đầu, dấu phần trăm và ngày theo style Excel
C. DataFormatter tự sửa tất cả công thức sai trước khi xuất workbook
D. Các cột được xem là số khi cần hiển thị trong báo cáo
Đáp án đúng: B

Khi import workbook lớn qua HTTP, phương án nào giúp tránh kiệt tài nguyên?
A. Giữ mọi workbook trên heap của server cho đến khi người dùng đăng xuất
B. Áp dụng hạn mức tệp, luồng đọc phù hợp và kiểm soát công việc xử lý
C. Tự tăng số lượng workbook được mở khi bộ nhớ còn ít để chia tải
D. Tạm ngừng bước xác thực để rút ngắn thời gian import workbook
Đáp án đúng: B

Khi thay đổi template báo cáo Excel, điều gì giúp phát hiện hồi quy?
A. Đổi toàn bộ tên sheet để người dùng không thể dùng lại tệp cũ
B. Loại công thức khỏi template để đơn giản hóa kiểm thử của nhóm
C. So sánh số dòng mã tạo báo cáo trước và sau khi chỉnh sửa
D. Kiểm thử hợp đồng cột, dữ liệu và định dạng trên tệp xuất mẫu
Đáp án đúng: D
