Câu 1: Interpreter Pattern phù hợp nhất với nhu cầu nào?
A. Đánh giá biểu thức của một ngôn ngữ nhỏ có grammar
B. Thay đổi thuật toán sắp xếp tại runtime theo context
C. Phân phối request qua nhiều handler kế tiếp nhau
D. Đóng gói thao tác người dùng để đưa vào queue
Đáp án đúng: A

Câu 2: Trong Interpreter, grammar đóng vai trò gì?
A. Cấp quyền truy cập database cho từng biểu thức
B. Định nghĩa cú pháp hợp lệ của các biểu thức
C. Quy định bố cục màn hình nhập các câu lệnh
D. Quy định thứ tự deploy của mọi module ứng dụng
Đáp án đúng: B

Câu 3: Với biểu thức 3 + x, node NumberLiteral(3) thường là gì?
A. Nonterminal expression chứa hai toán hạng con
B. Parser state dùng để lưu toàn bộ chuỗi token
C. Terminal expression không chứa node biểu thức con
D. Environment object chứa giá trị biến x
Đáp án đúng: C

Câu 4: Với biểu thức (a > 5) AND active, node AND thường thuộc loại nào?
A. Terminal expression không có biểu thức thành phần
B. Lexer token giữ đúng nguyên văn toàn biểu thức
C. Nonterminal expression kết hợp hai node con
D. Context object ánh xạ tên biến sang giá trị
Đáp án đúng: C

Câu 5: AST trong Interpreter chủ yếu thể hiện điều gì?
A. Lịch sử thay đổi source code của bộ thông dịch
B. Các bản ghi database được lọc bởi evaluator
C. Danh sách method chạy của Java thread hiện tại
D. Cấu trúc cú pháp phân cấp của biểu thức đã parse
Đáp án đúng: D

Câu 6: Lexer nên xử lý bước nào trước khi parser tạo AST?
A. Tính kết quả Boolean cuối cùng của biểu thức
B. Tự chạy hàm nghiệp vụ của mọi tên biến gặp
C. Biến input thành token như ID, NUMBER, OP
D. Tạo đối tượng Receiver để thực hiện Command
Đáp án đúng: C

Câu 7: Theo quy tắc ưu tiên toán học thông thường, 2 + 3 * 4 cho kết quả nào?
A. 20 vì luôn tính mọi toán tử từ trái sang phải
B. 14 vì phép nhân được ưu tiên trước phép cộng
C. 24 vì phép cộng luôn ưu tiên trước phép nhân
D. 9 vì mỗi operator chỉ dùng toán hạng gần nhất
Đáp án đúng: B

Câu 8: Với ngoặc của cùng grammar, (2 + 3) * 4 phải được đánh giá ra sao?
A. 14 vì nhân vẫn chạy trước khi xét dấu ngoặc
B. 24 vì parse tree luôn bỏ mọi dấu ngoặc
C. 9 vì evaluator chỉ đọc hai token đầu
D. 20 vì biểu thức trong ngoặc được tính trước
Đáp án đúng: D

Câu 9: Phép trừ kết hợp trái: 10 - 3 - 2 cho kết quả nào?
A. 9 theo phép tính 10 - (3 - 2)
B. 5 theo phép tính (10 - 3) - 2
C. 6 theo phép tính (10 - 2) - 2
D. 15 theo phép tính 10 + 3 + 2
Đáp án đúng: B

Câu 10: Khi dùng recursive-descent parser, grammar đệ quy trái trực tiếp có thể gây gì?
A. AST tự cân bằng độ sâu bằng rotation
B. Gọi đệ quy không tiến token và không kết thúc
C. Lexer mất khả năng nhận biết token NUMBER
D. Evaluator chuyển mọi phép toán thành phép cộng
Đáp án đúng: B

Câu 11: Trong pipeline xử lý biểu thức, parser khác evaluator ở nhiệm vụ nào?
A. Parser tạo cấu trúc; evaluator tính theo context
B. Parser chạy SQL; evaluator chỉ tách từ khóa đầu
C. Parser phân quyền; evaluator sinh mã giao diện
D. Parser ghi cache; evaluator chỉ sửa grammar text
Đáp án đúng: A

Câu 12: Với biểu thức age >= 18, giá trị age thường được lấy từ đâu lúc evaluate?
A. ClassLoader tự tra biến trong tất cả JVM thread
B. Lexer buộc ghi cứng age vào terminal string
C. Context ánh xạ tên biến sang giá trị hiện tại
D. Token age được coi luôn là số 18 mặc định
Đáp án đúng: C

Câu 13: Khi evaluate gặp tên biến chưa được khai báo trong context, xử lý nào đúng?
A. Tự mặc định mọi biến chưa có thành true
B. Tự tạo field cùng tên trên Java class bằng reflection
C. Bỏ toàn bộ nhánh logic chứa biến đó không báo lỗi
D. Báo lỗi biến không xác định theo hợp đồng
Đáp án đúng: D

Câu 14: Với biểu thức false AND riskyCheck(), short-circuit hợp lệ sẽ làm gì?
A. Không đánh giá riskyCheck() vì vế trái false
B. Vẫn gọi riskyCheck() để thu đủ dữ liệu lỗi
C. Đánh giá vế phải trước rồi mới đọc false
D. Biến mọi biểu thức AND thành giá trị true
Đáp án đúng: A

Câu 15: Với biểu thức true OR expensiveCheck(), short-circuit hợp lệ là gì?
A. Luôn gọi expensiveCheck() để xác định kiểu
B. Đổi phép OR thành AND khi vế trái true
C. Tạo lại toàn bộ AST cho mỗi lời gọi OR
D. Bỏ qua expensiveCheck() vì đã có true
Đáp án đúng: D

Câu 16: Khi biểu thức AND có node con là số nguyên thay vì Boolean, nên làm gì?
A. Tự đổi mọi số nguyên thành Boolean mà không báo
B. Áp dụng kiểm tra kiểu rồi báo lỗi không hợp lệ
C. Bỏ điều kiện AND và chỉ trả giá trị số nguyên
D. Đánh giá bằng so sánh địa chỉ các object Java
Đáp án đúng: B

Câu 17: Trong Java, interface Expression thường cung cấp phương thức gì?
A. dispatch(HttpRequest) để chọn REST controller
B. execute(Command) để chạy một Receiver cụ thể
C. save(EntityManager) để ghi AST vào database
D. evaluate(Context) trả giá trị của biểu thức
Đáp án đúng: D

Câu 18: Biểu thức phủ định NOT active nên được tạo AST theo cách nào?
A. Binary node Add chứa hai literal số
B. Terminal node Symbol chứa cả chuỗi NOT active
C. Unary node Not chứa một biểu thức con
D. Context node lưu một danh sách command
Đáp án đúng: C

Câu 19: Trong AST của phép cộng a + b, node Add thông thường cần gì?
A. Danh sách mọi lexer token trước khi parse
B. Hai node con và logic kết hợp giá trị của chúng
C. Một database connection gắn với mỗi số
D. Một HTTP controller riêng cho mỗi phép cộng
Đáp án đúng: B

Câu 20: Vì sao tách parser khỏi evaluator thường hữu ích?
A. Có thể parse một lần và đánh giá nhiều context
B. Mọi lần đánh giá bắt buộc đổi lại grammar
C. Parser tự tính giá trị mà không cần context
D. Evaluator chỉ xử lý chuỗi nguyên bản chưa parse
Đáp án đúng: A

Câu 21: Nếu AST được chia sẻ giữa nhiều luồng, đặc tính nào giúp an toàn hơn?
A. Node lưu kết quả cuối trong field mutable dùng chung
B. Node bất biến và context riêng cho mỗi lần đánh giá
C. Context static chứa giá trị biến của mọi request
D. Mỗi terminal node tự sửa grammar lúc evaluate
Đáp án đúng: B

Câu 22: Khi cùng một rule được chạy với nhiều bản ghi, tối ưu nào hợp lý?
A. Cache AST đã parse nếu grammar/rule không đổi
B. Parse chuỗi nguồn mới ở mỗi field của bản ghi
C. Biên dịch lại toàn bộ dự án Java mỗi lần đánh giá
D. Tạo thread mới cho từng token của cùng rule
Đáp án đúng: A

Câu 23: Parser gặp dấu ')' không khớp vị trí, thông tin lỗi nào hữu ích nhất?
A. Chỉ mã kết nối TCP hiện tại của client
B. Chỉ tên lớp Java sinh request bị lỗi
C. Vị trí token và cấu trúc cú pháp đang chờ
D. Chỉ tổng số dòng log trong quá trình chạy
Đáp án đúng: C

Câu 24: Với input có ngoặc lồng quá sâu từ người dùng, rủi ro quan trọng là gì?
A. Lexer luôn chuyển toàn bộ input thành giá trị true
B. AST luôn tự động có kích thước hằng số
C. Đệ quy parser/evaluator sâu gây cạn tài nguyên
D. Parser tự động ngắt mọi request HTTP khác
Đáp án đúng: C

Câu 25: Khi cho người dùng khai báo rule, cách nào hạn chế thực thi không an toàn?
A. Cho phép gọi method bất kỳ qua reflection
B. Đánh giá chuỗi bằng trình thực thi lệnh hệ điều hành
C. Cấp toàn bộ quyền database cho môi trường context
D. Whitelist toán tử/hàm và giới hạn tài nguyên
Đáp án đúng: D

Câu 26: Khi grammar ngày càng lớn và nhiều cú pháp phức tạp, cân nhắc nào phù hợp?
A. Thêm if vào một terminal node cho mọi rule mới
B. Bỏ bước parse rồi chạy từng token như command
C. Chỉ tăng số lớp con mà không kiểm thử grammar
D. Dùng parser generator hoặc giải pháp DSL chuyên dụng
Đáp án đúng: D

Câu 27: Bộ test cho parser biểu thức nên bao gồm trường hợp nào?
A. Ưu tiên, kết hợp, dấu ngoặc và cú pháp sai
B. Chỉ một biểu thức số nguyên không có toán tử
C. Chỉ cùng một AST đã được tạo thủ công trong test
D. Chỉ hiệu năng truy cập database độc lập grammar
Đáp án đúng: A

Câu 28: Kiểm thử evaluator độc lập parser hiệu quả bằng cách nào?
A. Tạo AST mẫu và thay context để so sánh kết quả
B. Chỉ chạy lexer rồi đo số token không lỗi
C. Chỉ so sánh chuỗi rule trước và sau minify
D. Chỉ gọi parser trên input trống để lấy exception
Đáp án đúng: A
