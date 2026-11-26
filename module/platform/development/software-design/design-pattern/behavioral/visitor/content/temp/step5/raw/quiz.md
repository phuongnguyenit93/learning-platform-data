Câu 1. Khi nhiều loại node AST cần thêm thao tác xuất mã, Visitor tách phần nào khỏi các node?
A. Khả năng tạo các node mới trong trình phân tích
B. Tách thao tác mới thành visitor trên cấu trúc node
C. Định nghĩa cấu trúc mỗi node ra khỏi lớp element
D. Mọi quan hệ cha-con của cây thành file cấu hình
Đáp án đúng: B

Câu 2. Trong triển khai Visitor Java cổ điển, lời gọi nào tạo bước phân phối thứ hai?
A. Visitor tự chọn kiểu node qua một chuỗi instanceof
B. Client gọi trực tiếp visit() không truyền node
C. Mỗi node trả class name để visitor dùng reflection
D. Element.accept(v) gọi v.visit(this) ở lớp cụ thể
Đáp án đúng: D

Câu 3. Vai trò chính của phương thức accept(Visitor) trên element là gì?
A. Lưu visitor trong trường static dùng chung hệ thống
B. Tự áp dụng mọi thao tác trước khi visitor được gọi
C. Gọi overload visit dành cho loại element cụ thể
D. Thay visitor bằng một subclass element mới ở runtime
Đáp án đúng: C

Câu 4. Để Visitor xử lý cả Circle và Rectangle, interface visitor nên có gì?
A. Một method visit() không tham số cho mọi element
B. Một method accept() bên trong chính visitor interface
C. Một factory tạo lại shape ở mỗi lời gọi visitor
D. Các method visit(Circle) và visit(Rectangle) riêng
Đáp án đúng: D

Câu 5. Khi bổ sung một phép thống kê mới lên cấu trúc phần tử ổn định, cách mở rộng đặc trưng là gì?
A. Thêm visitor mới, giữ nguyên các loại element
B. Thêm method thống kê vào từng node đã phát hành
C. Đổi class cha của toàn bộ phần tử đang tồn tại
D. Cho mỗi node tự chọn tên visitor theo cấu hình
Đáp án đúng: A

Câu 6. Nếu hệ thống thêm loại phần tử Triangle vào họ shape, đánh đổi quen thuộc của Visitor là gì?
A. Không cần chỉnh sửa bất kỳ visitor nào hiện có
B. Chỉ cần sửa cấu hình tạo đối tượng ở client
C. Các visitor cần bổ sung xử lý visit(Triangle)
D. Các operation phải chuyển thành static method
Đáp án đúng: C

Câu 7. Visitor phù hợp nhất với trường hợp phát triển nào?
A. Các loại element đổi liên tục, operation hiếm thay đổi
B. Tập loại element ổn định, nhiều operation mới
C. Chỉ có một element, không cần thao tác nào thêm
D. Các loại element và operation đều cố định mãi
Đáp án đúng: B

Câu 8. Vì sao Visitor có thể giữ các thao tác khỏi làm phình lớp element?
A. Logic xử lý được đặt trong các visitor chuyên biệt
B. Mọi element chuyển thành cấu trúc dữ liệu thuần JSON
C. Các method trên element được sinh tự động ở runtime
D. Visitor thay đổi danh tính element sau mỗi lần gọi
Đáp án đúng: A

Câu 9. Có thêm chức năng kiểm tra hợp lệ bên cạnh xuất HTML trên cùng cây, cách nào đúng tinh thần Visitor?
A. Chỉ thêm một nhánh if vào mọi node khi accept
B. Thêm subclass riêng cho từng node chỉ để validate
C. Đưa cả hai thuật toán vào constructor của element
D. Tạo ValidationVisitor độc lập với RenderVisitor
Đáp án đúng: D

Câu 10. Một visitor cần trả kết quả số nguyên cho mỗi node; thiết kế Java nào phù hợp?
A. Ép mọi phần tử ghi kết quả vào biến global dùng chung
B. Dùng generic visitor trả kết quả qua accept/visit
C. Bỏ phương thức accept và chỉ dùng Object.toString
D. Dùng nhiều constructor visitor để đoán kết quả
Đáp án đúng: B

Câu 11. Khi visitor duyệt cây có node chứa danh sách con, việc duyệt các con nên được thiết kế thế nào?
A. Luôn tự động do JVM gọi cho từng field được tham chiếu
B. Luôn phải nằm trong constructor của node cha
C. Quy định rõ traversal và gọi accept trên node con
D. Không thể dùng Visitor trên cây có quan hệ cha-con
Đáp án đúng: C

Câu 12. Nếu loại element thay đổi thường xuyên, phương án thay thế nào có thể đơn giản hơn Visitor?
A. Bắt buộc sinh visitor mới khi thêm mọi field
B. Dùng polymorphic method theo từng element
C. Luôn dùng reflection để truy cập mọi thuộc tính
D. Gắn tên method vào chuỗi rồi gọi trực tiếp
Đáp án đúng: B

Câu 13. Trong Java, tại sao chỉ gọi visitor.visit(element) khi biến element có kiểu interface có thể chưa đủ?
A. Overload được chọn theo kiểu tĩnh của đối số
B. JVM chọn overload bằng kiểu thực của đối số lúc runtime
C. Tất cả overload visit tự hợp thành một method duy nhất
D. Method overloading chỉ tồn tại với các lớp trừu tượng
Đáp án đúng: A

Câu 14. Mẫu double dispatch của Visitor chủ yếu kết hợp những gì?
A. Hai lần đọc cùng một giá trị từ database
B. Hai lần tạo cùng một node qua một factory
C. Hai lần override constructor trong class visitor
D. Dispatch qua accept rồi tới visit cho element cụ thể
Đáp án đúng: D

Câu 15. Khi visitor mới vô tình bỏ qua một element quan trọng, biện pháp nào giúp phát hiện sớm?
A. Khai báo đủ visit overload và test từng loại node
B. Đặt visit mặc định luôn rỗng mà không kiểm thử
C. Chỉ kiểm tra visitor có một constructor public
D. Cho element trả null cho mọi visitor chưa hỗ trợ
Đáp án đúng: A

Câu 16. Một visitor tích lũy tổng trên nhiều node và được chia sẻ giữa thread, vấn đề gì đáng lưu ý?
A. Node tự động đồng bộ mọi trường mutable của visitor
B. Accept luôn tạo bản sao visitor trước khi xử lý
C. State trong visitor cần cô lập hoặc đồng bộ
D. Kết quả visitor không thể dùng trong luồng song song
Đáp án đúng: C

Câu 17. Muốn test một Visitor xuất mã mà không phải dựng toàn bộ hệ thống biên dịch, cách nào hiệu quả?
A. Chỉ kiểm tra class visitor có tên đúng quy ước
B. Dùng reflection gọi visit với mọi đối tượng bất kỳ
C. Chỉ so thời gian dựng parser trước khi tạo AST
D. Dựng cây nhỏ xác định và so output của visitor
Đáp án đúng: D

Câu 18. Trong Visitor, nguyên tắc Open/Closed thường có đặc tính bất đối xứng nào?
A. Dễ thêm element mới, khó thêm thao tác mới
B. Mọi thay đổi đều không đụng vào mã đang chạy
C. Dễ thêm operation, thêm element phải sửa nhiều visitor
D. Visitor chỉ phát huy lợi ích khi không có interface
Đáp án đúng: C

Câu 19. Vì sao visitor cần truy cập quá nhiều field private có thể tạo đánh đổi?
A. Đòi lộ thêm dữ liệu element, làm tăng coupling
B. Các element không còn khả năng kế thừa interface
C. Các phép duyệt tự động thành bất đồng bộ
D. Mọi visitor bắt buộc chạy trên cùng một thread
Đáp án đúng: A

Câu 20. Một cây AST chứa chu kỳ tham chiếu, vì sao Visitor duyệt đệ quy ngây thơ có thể lỗi?
A. Java tự tạo visited set cho mọi accept method
B. Visitor luôn từ chối các node đã xử lý đúng một lần
C. Duyệt node có chu kỳ sẽ tự kết thúc sau hai lần
D. Có thể lặp vô hạn nếu không quản lý node đã thăm
Đáp án đúng: D

Câu 21. Trong một bộ Visitor, method visit(Leaf) có thể dùng cấu trúc nào để bảo đảm mỗi node được xử lý đúng?
A. Chỉ dựa vào tên class runtime của visitor
B. Dùng visited set/invariant để tránh xử lý trùng
C. Luôn gọi accept(this) hai lần để đối chiếu
D. Luôn gọi method visit(Object) trước mọi thao tác
Đáp án đúng: B

Câu 22. Khi Visitor thực hiện hành vi có side effect, test nào quan trọng ngoài kết quả trả về?
A. Kiểm tra số lần và thứ tự gọi lên các node
B. Chỉ so tên từng lớp trong cây AST
C. Chỉ biên dịch mọi visitor mà không chạy accept
D. Chỉ kiểm tra package name của các lớp element
Đáp án đúng: A

Câu 23. Nếu dùng một visitor cho cả xuất JSON và kiểm tra lỗi nghiệp vụ, dấu hiệu nên tách visitor là gì?
A. Hai thao tác luôn yêu cầu cùng một constructor
B. Visitor không có trường instance mutable nào
C. Hai trách nhiệm có lý do thay đổi khác nhau
D. Element đã được đánh dấu interface dùng chung
Đáp án đúng: C

Câu 24. Bài toán nào phù hợp với Visitor trên hệ thống biểu thức đại số?
A. Đưa cú pháp tất cả phép tính vào một parser static
B. Một visitor tính giá trị, một visitor in biểu thức
C. Thay mỗi node bằng một interface mới khi tính tổng
D. Gắn logic mọi phép xử lý vào constructor mỗi node
Đáp án đúng: B
