Câu 1: Khi trường CSV có dấu phẩy hoặc dấu xuống dòng, cách ghi phù hợp là gì?
A. Bao trường bằng dấu nháy kép và escape dấu nháy kép
B. Bỏ dấu phẩy rồi ghi trường CSV dưới dạng văn bản thường
C. Thay mọi xuống dòng bằng dấu cách trước khi xuất CSV
D. Bỏ dấu nháy kép rồi phân tách trường bằng khoảng trắng
Đáp án đúng: A

Câu 2: Trong CSV chuẩn, dấu nháy kép nằm trong giá trị được escape thế nào?
A. Dùng dấu gạch chéo trước nháy kép trong mọi trường CSV
B. Lặp đôi dấu nháy kép trong một trường được bao nháy
C. Dùng ký tự backtick thay dấu nháy kép trong dữ liệu
D. Đổi trường sang mã Base64 trước khi bao bằng nháy kép
Đáp án đúng: B

Câu 3: Vì sao không nên dùng String.split(",") để parse CSV tổng quát?
A. Nó không đọc được dấu phân cách trong các dòng trống
B. Nó tự chuyển tất cả các trường thành kiểu số nguyên
C. Nó không xử lý đúng dấu phân cách trong trường có nháy
D. Nó tự xóa toàn bộ dấu phân cách ở cuối từng bản ghi
Đáp án đúng: C

Câu 4: Khi bên gửi quy định UTF-8, cách đọc dữ liệu Java nào nhất quán?
A. Dùng charset mặc định của JVM khi tạo reader
B. Chỉ định StandardCharsets.UTF_8 khi tạo reader
C. Dùng charset của terminal hiện tại khi tạo reader
D. Dùng charset mặc định của hệ điều hành khi tạo reader
Đáp án đúng: B

Câu 5: Khi xử lý BOM UTF-8 ở đầu một file CSV, nên làm gì?
A. Xóa mọi byte giống BOM gặp trong toàn bộ nội dung file
B. Dùng BOM để suy đoán tên cột thay cho header thực tế
C. Nhận diện và bỏ BOM ở đầu luồng trước khi parse header
D. Chuyển BOM thành trường dữ liệu đầu tiên của bản ghi
Đáp án đúng: C

Câu 6: Nhập CSV từ nhiều nguồn có định dạng số khác nhau, nên xử lý thế nào?
A. Đọc số bằng locale mặc định và bỏ cảnh báo chuyển đổi
B. Loại bỏ mọi dấu phẩy trong dữ liệu trước khi parse số
C. Ép tất cả trường số về double rồi làm tròn khi lưu
D. Đặt locale và quy tắc phân tích số trong hợp đồng dữ liệu
Đáp án đúng: D

Câu 7: Khi đọc mảng JSON rất lớn bằng Jackson, kỹ thuật nào giảm RAM?
A. Nạp toàn bộ JSON vào JsonNode rồi quét từng phần tử
B. Chuyển JSON sang String lớn rồi chia thành các đoạn nhỏ
C. Nạp toàn bộ JSON vào Map trước khi duyệt từng khóa
D. Duyệt token bằng JsonParser thay vì giữ toàn cây JSON
Đáp án đúng: D

Câu 8: Với dữ liệu tiền tệ JSON cần giữ chính xác thập phân, nên dùng gì?
A. double với định dạng mặc định của JVM cho mọi phép tính
B. BigDecimal với chính sách scale và rounding rõ ràng
C. float với ép kiểu ngầm sang số nguyên ở bước cuối
D. String với so sánh từ điển thay cho phép tính số học
Đáp án đúng: B

Câu 9: Khi API gửi JSON thiếu field so với field có giá trị null, nên làm gì?
A. Xác định hai trường hợp trong hợp đồng mapping và validation
B. Luôn coi hai trường hợp bằng nhau trong mọi thao tác update
C. Tự đặt null cho mọi field không xuất hiện ở bất kỳ phiên bản
D. Tự chấp nhận giá trị thiếu là chuỗi rỗng trước khi lưu
Đáp án đúng: A

Câu 10: Khi import XML không đáng tin cậy, cấu hình parser cần ưu tiên gì?
A. Bật nạp thực thể ngoài để parser kiểm tra schema nhanh hơn
B. Cho parser truy cập tệp cục bộ để tự tìm dependency
C. Tự tải các DTD từ Internet nhằm tăng tính tương thích
D. Vô hiệu DTD và thực thể ngoài để chặn tấn công XXE
Đáp án đúng: D

Câu 11: Khi xử lý tệp XML lớn trong Java, lựa chọn nào hỗ trợ streaming?
A. Dùng DOM để tải toàn bộ cây XML vào bộ nhớ
B. Dùng XPath trên DOM đã nạp toàn bộ dữ liệu
C. Dùng StAX để đọc tuần tự các sự kiện của XML
D. Dùng JAXB để tạo mọi object trước khi xử lý
Đáp án đúng: C

Câu 12: Với tập Excel .xlsx lớn, cách đọc nào tránh nạp toàn workbook?
A. Dùng XSSFWorkbook rồi giữ mọi sheet trong bộ nhớ
B. Dùng DataFormatter rồi nhân bản toàn bộ workbook
C. Dùng workbook clone trước khi duyệt từng ô dữ liệu
D. Dùng cơ chế event/SAX phù hợp của Apache POI
Đáp án đúng: D

Câu 13: Khi xuất dữ liệu người dùng sang Excel, rủi ro nào cần kiểm soát?
A. Ô chứa dấu xuống dòng có thể tự xóa cả sheet dữ liệu
B. Ô chứa ký tự Unicode luôn làm hỏng file xlsx xuất ra
C. Ô bắt đầu bằng ký tự công thức có thể bị thực thi
D. Ô có số nguyên lớn luôn khiến workbook bị lỗi nén
Đáp án đúng: C

Câu 14: Khi import Excel chứa ô công thức, xử lý đúng tùy hợp đồng là gì?
A. Chọn rõ lấy công thức, cached value hay đánh giá công thức
B. Luôn xem mọi ô công thức là chuỗi nhập thủ công thông thường
C. Luôn tính lại công thức mà không xét dữ liệu bên ngoài
D. Luôn lấy giá trị hiển thị mà bỏ kiểu và vùng dữ liệu
Đáp án đúng: A

Câu 15: Vì sao header CSV cần được ánh xạ theo tên cột có kiểm tra?
A. Để phát hiện cột thiếu, cột lạ hoặc thứ tự cột thay đổi
B. Để mọi bản ghi có thể bỏ qua kiểm tra kiểu dữ liệu khi nhập
C. Để thứ tự cột luôn cố định dù hợp đồng có thể thay đổi
D. Để dữ liệu số không cần kiểm tra dấu phân cách thập phân
Đáp án đúng: A

Câu 16: Khi import bản ghi sai định dạng, cách báo lỗi nào hỗ trợ sửa dữ liệu?
A. Ghi duy nhất tổng số dòng sai mà không nêu trường nào sai
B. Ghi toàn bộ thông tin nhạy cảm của bản ghi vào log công khai
C. Ghi số dòng, tên trường và nguyên nhân lỗi có thể hành động
D. Ghi stack trace và yêu cầu người dùng tự suy ra lỗi dữ liệu
Đáp án đúng: C

Câu 17: Với hàng triệu bản ghi, vì sao nên validate theo luồng và từng lô?
A. Đảm bảo mọi bản ghi hợp lệ mà không phải kiểm tra schema
B. Loại bỏ mọi khóa trùng mà không cần quy tắc nhận diện
C. Bảo đảm rollback toàn bộ dữ liệu mà không cần giao dịch
D. Giảm bộ nhớ đỉnh và cho phép xử lý lỗi theo từng lô
Đáp án đúng: D

Câu 18: Khi import dữ liệu trùng ID, quyết định nào cần ghi trong hợp đồng?
A. Chọn từ chối, bỏ qua hay cập nhật theo chính sách rõ ràng
B. Tự động thêm hậu tố ngẫu nhiên cho mọi khóa bị trùng
C. Luôn ghi đè bản ghi cũ dù nguồn nhập chưa được tin cậy
D. Luôn bỏ qua khóa trùng mà không lưu lại lý do xử lý
Đáp án đúng: A

Câu 19: Nếu nhập theo lô và lô thứ ba lỗi, chiến lược transaction nên xác định gì?
A. Chỉ tăng số kết nối database để lô tiếp theo chạy nhanh
B. Ranh giới commit/rollback và khả năng chạy lại các lô
C. Chỉ đổi tên file nguồn rồi chạy lại toàn bộ mà không kiểm tra
D. Chỉ ghi log thành công dù lô lỗi chưa được xử lý
Đáp án đúng: B

Câu 20: Để chạy lại import sau lỗi mà không nhân đôi dữ liệu, cần gì?
A. Sử dụng UUID mới cho mọi bản ghi trong mỗi lần retry
B. Khóa idempotency hay cơ chế upsert có kiểm soát
C. Bỏ toàn bộ kiểm tra khóa duy nhất để tăng tốc import
D. Ghi đè timestamp mọi bản ghi trước khi thử lại
Đáp án đúng: B

Câu 21: Khi export dữ liệu lớn qua HTTP, cách giảm tiêu thụ RAM là gì?
A. Tạo một byte array toàn bộ dữ liệu rồi mới trả response
B. Chuyển toàn bộ output thành String trước khi ghi network
C. Nạp toàn bộ dữ liệu và sinh thêm bản sao trước khi ghi
D. Ghi tuần tự vào output stream thay vì tạo toàn file RAM
Đáp án đúng: D

Câu 22: Khi sinh file export có thể bị ngắt giữa chừng, cách xuất an toàn là gì?
A. Ghi file tạm, xác minh hoàn chỉnh rồi đổi tên thành file đích
B. Ghi trực tiếp vào file đích cho mỗi hàng để luôn sẵn sàng
C. Ghi file đích trước rồi kiểm tra checksum khi có lỗi
D. Ghi đè file cũ ngay khi bắt đầu để báo quá trình đang chạy
Đáp án đúng: A

Câu 23: Khi trao đổi dữ liệu theo các phiên bản schema, cần đặc tả điều gì?
A. Chỉ thứ tự các khóa JSON mà không nêu kiểu và ràng buộc
B. Trường bắt buộc, trường tùy chọn và chiến lược tương thích
C. Chỉ tên file cuối cùng mà không nêu định dạng bản ghi
D. Chỉ tên biến trong Java mà không nêu thay đổi của schema
Đáp án đúng: B

Câu 24: Với định dạng Avro có writer schema và reader schema, lợi ích nào đúng?
A. Cho phép bỏ mọi trường bắt buộc dù reader không có default
B. Cho phép lưu mọi object mà không cần biết kiểu dữ liệu
C. Cho phép giải mã theo quy tắc tương thích giữa hai schema
D. Cho phép đọc mọi file nhị phân bằng một schema tùy ý
Đáp án đúng: C

Câu 25: Với dữ liệu phân tích dạng cột, lợi ích phổ biến của Parquet là gì?
A. Đọc bản ghi theo thứ tự nhập và giữ mọi byte nguyên dạng
B. Luôn tối ưu cập nhật từng dòng theo khóa primary key
C. Đọc cột cần thiết và dùng nén/mã hóa theo cột
D. Luôn hỗ trợ giao dịch nhiều bảng trực tiếp trong file
Đáp án đúng: C

Câu 26: Khi xuất dữ liệu thời gian cho hệ thống khác, cách biểu diễn nào giảm mơ hồ?
A. Chuỗi ngày giờ theo locale hiện tại của máy chủ
B. Chuỗi ngày giờ thiếu múi giờ và tự suy từ thiết bị
C. Số giờ địa phương mà không có ngày hay offset
D. ISO 8601 có offset hoặc UTC theo hợp đồng trao đổi
Đáp án đúng: D

Câu 27: Vì sao cần kiểm tra checksum file trước và sau bước truyền dữ liệu?
A. Chứng minh người gửi đã được xác thực trong mọi trường hợp
B. Phát hiện file bị thay đổi hoặc hỏng trong lúc truyền
C. Chứng minh nội dung có schema hợp lệ ở từng bản ghi
D. Thay thế hoàn toàn cơ chế ký số khi có yêu cầu xác thực
Đáp án đúng: B

Câu 28: Khi import chứa PII, cách ghi audit log nào hợp lý?
A. Ghi mã lô, tổng kết và lỗi đã che dữ liệu nhạy cảm
B. Ghi nguyên nội dung mọi dòng nhập vào log hệ thống chung
C. Ghi mật khẩu và token nguồn để tiện chạy lại import
D. Ghi cả file nguồn vào log để khôi phục không cần backup
Đáp án đúng: A
