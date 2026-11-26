Câu 1. Phân biệt cú pháp và ngữ nghĩa của ngôn ngữ lập trình như thế nào?
A. Cú pháp quy định kết quả, ngữ nghĩa quy định dấu câu
B. Cú pháp mô tả bộ nhớ, ngữ nghĩa xác định token
C. Cú pháp là cấu trúc, ngữ nghĩa là hành vi
D. Cú pháp đo hiệu năng, ngữ nghĩa đo độ dài lệnh
Đáp án đúng: C

Câu 2. Lợi ích đặc trưng của kiểm tra kiểu tĩnh là gì?
A. Phát hiện một số lỗi kiểu trước khi thực thi
B. Đảm bảo chương trình không có lỗi nghiệp vụ
C. Luôn loại bỏ hoàn toàn việc kiểm tra lúc chạy
D. Tự suy diễn tất cả giao thức mạng khi biên dịch
Đáp án đúng: A

Câu 3. Trong lexical scoping, một biến tự do trong hàm thường được tìm ở đâu?
A. Phạm vi của hàm đã gọi nó gần nhất
B. Phạm vi của luồng đang thực thi hàm
C. Phạm vi của đối tượng cấp phát gần đây
D. Phạm vi tại chỗ khai báo hàm trong mã
Đáp án đúng: D

Câu 4. Dynamic scoping khác lexical scoping chủ yếu tại điểm nào?
A. Tra cứu biến dựa vào chuỗi lời gọi hiện hành
B. Tra cứu biến dựa vào vị trí khai báo trong mã
C. Tra cứu biến dựa vào địa chỉ vật lý trong heap
D. Tra cứu biến dựa vào thứ tự khai báo kiểu dữ liệu
Đáp án đúng: A

Câu 5. Một closure thường mang theo những thành phần nào?
A. Thân hàm và trạng thái của mọi thread
B. Thân hàm cùng môi trường biến được giữ lại
C. Thân hàm và danh sách mọi module đã nạp
D. Thân hàm và vùng nhớ toàn bộ tiến trình
Đáp án đúng: B

Câu 6. Khi khai báo biến x trong khối con trùng tên x của khối ngoài, điều gì xảy ra?
A. Biến ngoài tự chuyển thành giá trị hằng
B. Biến ngoài bị xóa khỏi bộ nhớ ngay lập tức
C. Biến trong che tên biến ngoài tại khối đó
D. Biến trong tự dùng chung địa chỉ với biến ngoài
Đáp án đúng: C

Câu 7. Với Java, truyền một tham chiếu đối tượng làm tham số có nghĩa gì?
A. Tham số trỏ trực tiếp tới biến của caller
B. Giá trị tham chiếu được sao chép cho hàm
C. Một đối tượng mới được sao chép sâu vào hàm
D. Biến caller luôn đổi khi gán lại tham số
Đáp án đúng: B

Câu 8. Hai biến cùng tham chiếu một đối tượng mutable có rủi ro gì?
A. Hai biến luôn được cấp phát hai heap riêng
B. Mọi thay đổi trên đối tượng đều bị bỏ qua
C. Trình biên dịch luôn tách các đối tượng ra
D. Sửa đối tượng qua một biến ảnh hưởng biến kia
Đáp án đúng: D

Câu 9. Trong mô hình runtime phổ biến, call stack thường chứa dữ liệu nào?
A. Khung gọi chứa địa chỉ trả về và biến cục bộ
B. Mọi đối tượng còn sống qua nhiều lời gọi hàm
C. Toàn bộ mã nguồn của chương trình và thư viện
D. Tất cả dữ liệu đã ghi lên hệ thống tệp vật lý
Đáp án đúng: A

Câu 10. Garbage collector dựa trên reachability có thể thu gom khi nào?
A. Đối tượng vẫn còn được root tham chiếu tới
B. Đối tượng không còn đường tới từ các GC root
C. Đối tượng có nhiều tham chiếu từ các object khác
D. Đối tượng vừa được truyền qua tham số của hàm
Đáp án đúng: B

Câu 11. Suy luận kiểu trong ngôn ngữ có hệ kiểu tĩnh thường có nghĩa gì?
A. Kiểu chỉ được gán lần đầu khi chương trình chạy
B. Mọi biến đều nhận kiểu động và thay đổi tùy ý
C. Compiler xác định kiểu từ biểu thức và ràng buộc
D. Compiler bỏ qua kiểm tra kiểu cho các biến suy ra
Đáp án đúng: C

Câu 12. Parametric polymorphism cho phép điều gì?
A. Hàm tự chọn các nhánh theo lớp runtime của đối số
B. Một cài đặt dùng với nhiều kiểu qua tham số kiểu
C. Hàm tự đổi tên kiểu theo chuỗi đầu vào khi chạy
D. Mỗi kiểu luôn cần một bản sao mã thủ công riêng
Đáp án đúng: B

Câu 13. Thay thế một subtype cho base type an toàn đòi hỏi điều gì?
A. Subtype luôn có nhiều trường dữ liệu hơn base
B. Subtype được phép đổi mọi hậu điều kiện của base
C. Subtype chỉ dùng phương thức private của chính nó
D. Subtype giữ các cam kết hành vi mà base yêu cầu
Đáp án đúng: D

Câu 14. Kiểu tổng (sum type) như Either<Error,Value> biểu diễn điều gì?
A. Giá trị thuộc một trong các nhánh được khai báo
B. Giá trị luôn giữ đồng thời cả hai nhánh dữ liệu
C. Giá trị chỉ có thể tạo bằng phép cộng số nguyên
D. Giá trị luôn phải chứa một danh sách các kiểu
Đáp án đúng: A

Câu 15. Kiểm tra exhaustive pattern matching với enum giúp phát hiện điều gì?
A. Trình tự khớp mẫu chạy theo thời gian tuyến tính
B. Mọi mẫu có thể được chạy trên nhiều thread đồng thời
C. Bộ nhớ dành cho mọi biến thể được cấp phát bằng nhau
D. Một hoặc nhiều biến thể chưa được xử lý trong match
Đáp án đúng: D

Câu 16. Referential transparency của biểu thức thuần có ý nghĩa nào?
A. Thay biểu thức bằng tên biến mà không cần kiểu dữ liệu
B. Thay biểu thức bằng mã bytecode nhưng vẫn giữ cú pháp
C. Có thể thay biểu thức bằng giá trị mà giữ hành vi
D. Thay biểu thức bằng lời gọi I/O nhưng kết quả vẫn cố định
Đáp án đúng: C

Câu 17. Call-by-need khác eager evaluation ở điểm cơ bản nào?
A. Đánh giá đối số trước cả khi gọi hàm
B. Chỉ tính khi cần và ghi nhớ kết quả tính
C. Tính lại đối số ở mỗi lần dùng trong hàm
D. Luôn tính mọi nhánh điều kiện trước khi chọn
Đáp án đúng: B

Câu 18. Hàm bậc cao được nhận diện bằng đặc điểm nào?
A. Nhận hàm làm tham số hoặc trả về một hàm
B. Luôn chạy nhanh hơn hàm có tham số dữ liệu
C. Chỉ tồn tại trong ngôn ngữ có hệ kiểu động
D. Luôn yêu cầu người dùng khai báo lớp cha
Đáp án đúng: A

Câu 19. Trả Result<Value,Error> thay vì ném exception thể hiện hướng xử lý nào?
A. Lỗi bắt buộc bị bỏ qua ở phần gọi hàm
B. Lỗi tự động được sửa bằng runtime của ngôn ngữ
C. Thành công hoặc lỗi được biểu diễn bằng giá trị
D. Trạng thái lỗi được chuyển thành log toàn cục
Đáp án đúng: C

Câu 20. Hai thread ghi đọc cùng một biến chia sẻ mà thiếu đồng bộ có thể gặp gì?
A. Data race cho kết quả phụ thuộc lịch thực thi
B. Dead code khiến compiler tự xóa mọi truy cập
C. Memory leak xảy ra ở mọi lần đọc dữ liệu
D. Stack overflow ngay khi tạo thread thứ hai
Đáp án đúng: A

Câu 21. Trong mô hình async/await phổ biến, await trên tác vụ chưa hoàn tất làm gì?
A. Chặn toàn bộ tiến trình đến khi tác vụ kết thúc
B. Gọi lại toàn bộ chương trình từ điểm vào ban đầu
C. Sao chép toàn bộ heap của thread đang thực thi
D. Tạm dừng tác vụ để chờ kết quả bất đồng bộ
Đáp án đúng: D

Câu 22. Hygienic macro chủ yếu giải quyết vấn đề gì khi mở rộng mã?
A. Tránh tạo thêm bytecode so với hàm thông thường
B. Tránh bắt nhầm biến do xung đột tên khi mở rộng
C. Tránh nạp thêm thư viện trong bước liên kết build
D. Tránh kiểm tra kiểu cho mọi biểu thức được tạo ra
Đáp án đúng: B

Câu 23. Điểm khác biệt điển hình giữa internal DSL và external DSL là gì?
A. Internal DSL luôn được chạy nhanh hơn external DSL
B. Internal DSL bắt buộc có parser ngữ pháp hoàn toàn riêng
C. Internal DSL tận dụng cú pháp của ngôn ngữ chủ
D. Internal DSL không thể mô tả quy tắc nghiệp vụ
Đáp án đúng: C

Câu 24. Đối với ngôn ngữ biên dịch sang bytecode rồi chạy trên VM, nhận định nào đúng?
A. VM chỉ đọc mã nguồn mà không nạp bytecode
B. Bytecode luôn là mã máy cho duy nhất một CPU
C. Biên dịch bytecode loại bỏ mọi bước thực thi runtime
D. VM thực thi bytecode bằng thông dịch hoặc JIT
Đáp án đúng: D
