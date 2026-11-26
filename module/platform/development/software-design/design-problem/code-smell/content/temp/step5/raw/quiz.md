Câu 1: Code smell được hiểu phù hợp nhất là gì trong quá trình review?
A. Bằng chứng chắc chắn chương trình đang có bug
B. Một lỗi cú pháp do compiler Java phát hiện
C. Dấu hiệu gợi ý cần điều tra thiết kế và rủi ro
D. Một cảnh báo bảo mật luôn nghiêm trọng như nhau
Đáp án đúng: C

Câu 2: Một method dài trộn xác thực, tính phí và gửi mail cho thấy smell nào rõ nhất?
A. Feature Envy vì chỉ đọc một object khác
B. Long Method có nhiều giai đoạn trách nhiệm
C. Data Clumps vì luôn có dữ liệu cùng xuất hiện
D. Message Chains vì có nhiều delegate nối tiếp
Đáp án đúng: B

Câu 3: Refactoring nào thường là bước đầu với Long Method có các bước độc lập?
A. Move Field vào mọi class đang gọi method
B. Extract Method và đặt tên cho từng ý định
C. Replace Constructor with Factory Method
D. Introduce Parameter Object cho tất cả biến
Đáp án đúng: B

Câu 4: Một method 80 dòng nhưng là bảng tra cứu rõ ràng, ít thay đổi cần đánh giá thế nào?
A. Xóa ngay vì số dòng vượt ngưỡng mặc định
B. Tách mỗi câu lệnh thành một public method
C. Chuyển method thành 80 class theo từng dòng
D. Dựa vào độ phức tạp và chi phí thay đổi thực
Đáp án đúng: D

Câu 5: Large Class thường được nhận diện bằng loại bằng chứng nào?
A. Các field/method thuộc nhóm trách nhiệm khác nhau
B. Chỉ số lượng dòng import trong file Java
C. Tên class chứa nhiều hơn hai từ viết hoa
D. Chỉ số bytecode phát sinh từ một constructor
Đáp án đúng: A

Câu 6: Khi một Large Class gồm logic xuất PDF và tính thuế riêng biệt, refactor nào hợp lý?
A. Inline toàn bộ method vào một constructor
B. Replace Data Value with Object trên mọi field
C. Pull Up Method lên superclass không liên quan
D. Extract Class theo hai nhóm trách nhiệm rõ
Đáp án đúng: D

Câu 7: Hai service chứa cùng công thức tính phí được copy-paste, smell nào chính?
A. Duplicate Code làm việc sửa rule dễ lệch
B. Primitive Obsession vì công thức trả số
C. Feature Envy vì mỗi service có field riêng
D. Temporary Field vì hàm có biến cục bộ
Đáp án đúng: A

Câu 8: Cách xử lý Duplicate Code xuất hiện ở hai nơi có cùng quy tắc là gì?
A. Đổi tên biến hai nơi rồi giữ nguyên từng công thức
B. Copy thêm sang ba service khác để đồng bộ quy tắc
C. Extract Function/Component chung nếu ngữ nghĩa thực sự trùng
D. Dùng reflection gọi các đoạn source giống nhau
Đáp án đúng: C

Câu 9: Vì sao không nên xóa mọi đoạn code giống nhau một cách máy móc?
A. Java không cho phép trùng nội dung trong hai file
B. Compiler luôn loại bỏ được mọi đoạn code trùng
C. Tất cả đoạn giống chữ đều có cùng domain rule
D. Ngữ nghĩa và nhịp thay đổi có thể khác nhau
Đáp án đúng: D

Câu 10: Một method của OrderService liên tục gọi getter của Customer để tính giá theo dữ liệu Customer là gợi ý gì?
A. Feature Envy: hành vi có thể đặt gần Customer
B. Long Parameter List vì service không truyền tham số
C. Lazy Class vì Customer có quá nhiều business rule
D. Message Chains vì service gọi nhiều static field
Đáp án đúng: A

Câu 11: Khi xác nhận Feature Envy, câu hỏi cần kiểm tra trước Move Method là gì?
A. Số dòng code chuyển sang class khác có bằng nhau không
B. Hành vi dùng dữ liệu bên nào và thuộc trách nhiệm nào
C. Số lượng getter có tăng lên sau lần build cuối không
D. Method có được gọi từ đúng một controller không
Đáp án đúng: B

Câu 12: Một chỉnh sửa tên trường discount làm phải sửa 12 lớp ở các package không liên quan gợi ý gì?
A. Divergent Change vì một class đổi bởi nhiều lý do
B. Large Class vì tất cả lớp đều có nhiều method
C. Shotgun Surgery do thay đổi lan ra nhiều nơi
D. Lazy Class vì mỗi lớp chỉ có đúng một method
Đáp án đúng: C

Câu 13: Shotgun Surgery khác Divergent Change theo vị trí sửa đổi như thế nào?
A. Cả hai đều chỉ có nghĩa một method quá dài
B. Shotgun Surgery chỉ xảy ra trong database
C. Nhiều lớp cùng sửa; một lớp đổi nhiều lý do
D. Divergent Change chỉ phát sinh với interface
Đáp án đúng: C

Câu 14: Một lớp UserManager phải thay khi đổi UI, SQL và quy tắc quyền là smell nào?
A. Feature Envy vì class chỉ dùng dữ liệu User
B. Divergent Change vì một class đổi bởi nhiều concern
C. Message Chains vì controller có nhiều request
D. Data Clumps vì nhiều tham số cùng xuất hiện
Đáp án đúng: B

Câu 15: Các tham số street, city, zip luôn được truyền cùng nhau qua nhiều method gợi ý gì?
A. Lazy Class vì Address chưa có method xử lý
B. Data Clumps có thể dùng Address value object
C. Middle Man vì ba tham số được truyền qua nhau
D. Shotgun Surgery vì luôn có đúng ba tham số
Đáp án đúng: B

Câu 16: Khi method có 12 tham số, lựa chọn cải tiến phù hợp nếu các nhóm dữ liệu có ý nghĩa là gì?
A. Đưa tất cả giá trị vào static biến dùng chung
B. Tự thay mọi tham số thành Object không kiểu
C. Introduce Parameter Object cho nhóm thông tin liên quan
D. Xóa bớt tham số dù vẫn cần cho nghiệp vụ
Đáp án đúng: C

Câu 17: Dùng String cho cả email, currency và orderId không kiểm tra ràng buộc gợi ý gì?
A. Primitive Obsession: thiếu value type mang ý nghĩa
B. Feature Envy vì primitive là thuộc tính hệ thống
C. Message Chains vì String có nhiều method public
D. Large Class vì ba trường nằm cùng một object
Đáp án đúng: A

Câu 18: Khi client gọi a.getB().getC().getD().execute() ở nhiều nơi, smell nào nổi bật?
A. Duplicated Condition vì có nhiều lệnh if giống nhau
B. Temporary Field vì chỉ dùng field lúc thực thi
C. Switch Statement vì lựa chọn hành vi bằng enum
D. Message Chains làm lộ cấu trúc đối tượng bên trong
Đáp án đúng: D

Câu 19: Refactor nào thường giảm Message Chains khi client cần một hành động cấp cao?
A. Expose thêm getter ở mỗi mắt xích trong chuỗi
B. Đổi toàn bộ các thuộc tính thành static public
C. Hide Delegate để giấu chuỗi gọi bên trong
D. Chuyển tất cả getter thành constructor mới
Đáp án đúng: C

Câu 20: Một class chỉ chuyển gần như mọi lời gọi tới một dependency không thêm giá trị có thể là smell gì?
A. Feature Envy vì lớp dùng nhiều object khác
B. Long Method vì forward có độ phức tạp cao
C. Data Clumps vì nhiều tham số được chuyền qua
D. Middle Man vì lớp hầu như chỉ chuyển tiếp
Đáp án đúng: D

Câu 21: Temporary Field thường chỉ điều gì?
A. Field chỉ hợp lệ trong một vài pha xử lý hiếm
B. Field được gán giá trị mặc định trong constructor
C. Field được đọc liên tục bởi các request khác nhau
D. Field là hằng số không đổi của domain object
Đáp án đúng: A

Câu 22: Khi một comment dài phải giải thích nhiều nhánh điều kiện khó hiểu, nên làm gì trước?
A. Xem xét Decompose Conditional và tên có nghĩa
B. Xóa comment rồi giữ nguyên nhánh phức tạp
C. Thêm comment tương tự ở toàn bộ call sites
D. Tự thay mọi nhánh bằng reflection dynamic
Đáp án đúng: A

Câu 23: Chỉ số cyclomatic complexity cao trong một method nên được hiểu ra sao?
A. Là chứng minh method đang trả kết quả sai
B. Báo hiệu nhiều nhánh cần review và test
C. Là bảo đảm method không thể được unit test
D. Là căn cứ đủ để rewrite toàn bộ codebase
Đáp án đúng: B

Câu 24: Khi test legacy code chưa có đặc tả đáng tin, bước nào hữu ích trước khi tách method?
A. Đổi mọi kết quả trả về theo định dạng mới
B. Xóa code chưa có test để giảm technical debt
C. Viết test ghi nhận hành vi hiện tại
D. Sửa đồng thời schema và API trong một thay đổi
Đáp án đúng: C

Câu 25: Điều gì xác nhận một refactor đã giữ nguyên hành vi quan sát được?
A. Số dòng mã luôn giảm ít nhất một nửa
B. Số lượng method mới luôn nhiều hơn trước
C. Mọi class đều phải có một interface mới
D. Chạy regression test và so sánh kết quả
Đáp án đúng: D

Câu 26: Để ưu tiên sửa code smell, yếu tố thực tế nào nên xem xét?
A. Tần suất đổi mã, rủi ro và chi phí kiểm thử
B. Chỉ số lượng dòng code được editor tô màu
C. Chỉ số cảnh báo linter mà không xem bối cảnh
D. Chỉ số interface xuất hiện trong toàn repository
Đáp án đúng: A

Câu 27: Một block switch theo enum hiếm đổi có phải luôn là smell cần loại bỏ không?
A. Có, mọi switch bắt buộc thay bằng Visitor
B. Có, switch không được phép viết trong Java
C. Không, vì mọi switch đều tối ưu hơn polymorphism
D. Không, cần xét độ ổn định và khả năng mở rộng
Đáp án đúng: D

Câu 28: Sau khi Extract Class để chữa Large Class, dấu hiệu nào cho thấy refactor chưa tốt?
A. Hai lớp có tên thể hiện một trách nhiệm riêng
B. Hai lớp vẫn phụ thuộc sâu vào dữ liệu nhau
C. Test nghiệp vụ trước và sau vẫn giữ kết quả
D. Mỗi lớp sở hữu dữ liệu nó trực tiếp xử lý
Đáp án đúng: B
