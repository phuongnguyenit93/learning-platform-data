DSL chủ yếu đem lại giá trị nào khi diễn đạt quy tắc nghiệp vụ?
A. Biểu đạt quy tắc theo từ vựng nghiệp vụ
B. Thay toàn bộ cơ chế chạy của ngôn ngữ nền
C. Loại bỏ hoàn toàn bước kiểm tra đầu vào
D. Bắt mọi tác vụ nghiệp vụ chạy song song
Đáp án đúng: A

Internal DSL thường có đặc điểm nào?
A. Có cú pháp độc lập với mọi ngôn ngữ chủ
B. Bắt buộc chạy qua lexer/parser tự viết
C. Chỉ chứa tệp cấu hình XML hoặc YAML
D. Dựa vào cú pháp của ngôn ngữ chủ
Đáp án đúng: D

External DSL khác internal DSL chủ yếu ở điểm nào?
A. Là tập method có trong class của ứng dụng
B. Chỉ chạy khi biên dịch thành bytecode Java
C. Phụ thuộc hoàn toàn vào cú pháp Java gốc
D. Có cú pháp riêng và phải tự phân tích
Đáp án đúng: D

Khi xây từ vựng cho DSL, lựa chọn nào giúp người dùng miền hiểu quy tắc?
A. Đặt từ khóa theo tên hàm nội bộ dự án
B. Giữ từng quy tắc trong chuỗi không có tên
C. Dùng từ vựng miền ổn định và rõ nghĩa
D. Dùng tên bảng cơ sở dữ liệu cho mọi quy tắc
Đáp án đúng: C

Trong một external DSL, bộ phân tích từ vựng (lexer) có nhiệm vụ nào?
A. Gắn ý nghĩa nghiệp vụ cho từng rule
B. Đánh giá biểu thức AST để trả kết quả
C. Tách chuỗi ký tự thành token có loại
D. Sinh mã máy cho trình thông dịch DSL
Đáp án đúng: C

Parser của external DSL thường thực hiện thao tác nào?
A. Tính kết quả biểu thức khi có dữ liệu
B. Dựng cây cú pháp theo quy tắc ngữ pháp
C. Kết nối mọi rule với bảng dữ liệu ngoài
D. Chọn phiên bản runtime để tải thư viện
Đáp án đúng: B

AST giúp biểu diễn biểu thức DSL theo cách nào?
A. Giữ nguyên mọi khoảng trắng và dấu phân cách
B. Dựng cây node cho cấu trúc biểu thức
C. Lưu mọi token theo thứ tự chưa phân nhóm
D. Đảm bảo mọi biểu thức đều đúng kiểu dữ liệu
Đáp án đúng: B

Sau khi parse thành công, kiểm tra ngữ nghĩa tĩnh có thể làm gì?
A. Đối chiếu kiểu và tên tham chiếu trong AST
B. Tách chuỗi ký tự thành từ khóa và literal
C. Sắp xếp câu lệnh theo vị trí trong tệp
D. Chọn cách xuống dòng cho tệp cấu hình
Đáp án đúng: A

Trình thông dịch DSL thường xử lý cấu trúc đã parse thế nào?
A. Chỉ lưu lại các ký tự gốc của source DSL
B. Chỉ kiểm tra thứ tự token trong tập tin
C. Chỉ chuyển mọi rule thành tài liệu Markdown
D. Duyệt AST để áp dụng các quy tắc
Đáp án đúng: D

Bộ sinh mã (code generator) cho DSL thường thực hiện điều gì?
A. Chuyển AST sang mã cho nền tảng đích
B. Chỉ sửa khoảng trắng trong source DSL
C. Chỉ kiểm tra input có trùng từ khóa
D. Chỉ hiển thị rule từ cơ sở dữ liệu
Đáp án đúng: A

Khi người dùng nhập rule DSL để hệ thống thực thi, biện pháp nào giảm rủi ro?
A. Chặn thao tác ngoài quyền, đặt hạn mức thực thi
B. Cho phép gọi mọi API nếu cú pháp DSL hợp lệ
C. Tin tưởng dữ liệu do người dùng gửi khi parse xong
D. Bỏ ghi log để giảm rò rỉ thông tin thực thi
Đáp án đúng: A

Để DSL không biến giá trị người dùng thành mã lệnh nguy hiểm, nên làm gì?
A. Ghép nguyên văn chuỗi DSL vào câu lệnh SQL
B. Chuyển literal thành code rồi mới thực thi
C. Ràng buộc giá trị qua API có tham số
D. Chỉ ẩn đầu vào DSL khỏi giao diện quản trị
Đáp án đúng: C

Nếu ngữ pháp DSL không xác định ưu tiên toán tử, rủi ro nào xuất hiện?
A. Mọi toán tử luôn được tính cùng thứ tự ưu tiên
B. Cùng biểu thức có thể có các cây phân tích khác
C. Các identifier tự động biến thành từ khóa cố định
D. Mọi câu lệnh phải được chạy theo thứ tự tệp
Đáp án đúng: B

Muốn mở rộng cú pháp DSL mà hạn chế phá vỡ các rule cũ, nên làm gì?
A. Đổi cú pháp tùy ý và chỉ kiểm tra các luật mới
B. Xóa grammar cũ rồi nhập lại toàn bộ luật
C. Đánh phiên bản ngữ pháp, thử lại các luật cũ
D. Chỉ đo tốc độ parser sau khi đổi cú pháp
Đáp án đúng: C

Thông báo lỗi cho người viết DSL nên ưu tiên điều gì?
A. In call stack Java cho mọi lỗi người dùng
B. Chỉ rõ vị trí và ý nghĩa lỗi trong DSL
C. Chỉ trả mã lỗi chung, không báo vị trí source
D. Tự bỏ qua token lạ rồi thực thi phần còn lại
Đáp án đúng: B

Trường hợp nào nên cân nhắc chưa thiết kế external DSL riêng?
A. Miền có từ vựng ổn định và nhiều quy tắc lặp lại
B. Người dùng nghiệp vụ cần đọc quy tắc rõ ràng
C. Những rule có thể kiểm chứng bằng bộ test ổn định
D. Miền rất ít luật, còn đổi nhiều, chi phí DSL cao
Đáp án đúng: D
