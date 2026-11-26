1. Mục tiêu của mẫu Prototype khi cần tạo đối tượng mới là gì?
A. Tạo bản mới dựa trên một object mẫu đã có cấu hình
B. Tạo sản phẩm qua override của phương thức ở Creator
C. Tạo đối tượng bằng chuỗi bước cấu hình Builder
D. Dùng chung một instance cho toàn bộ chương trình
Đáp án đúng: A

2. Điều kiện tối thiểu nào xác nhận phép copy tạo ra đối tượng mới?
A. Bản copy phải có mọi giá trị field khác bản gốc
B. Bản copy phải thuộc một subtype khác với bản gốc
C. Đối tượng kết quả có identity khác với bản gốc
D. Bản copy phải được đăng ký trong một global cache
Đáp án đúng: C

3. Một shallow copy của object chứa `List<Item>` thường có đặc tính gì?
A. Object mới và clone đệ quy mọi Item trong List
B. Object mới nhưng cùng tham chiếu tới List ban đầu
C. Object cũ chỉ đổi tham chiếu đến List khác
D. Object mới không giữ bất kỳ field nào của bản gốc
Đáp án đúng: B

4. Khi shallow copy chứa List mutable, lỗi nào dễ xuất hiện?
A. Dữ liệu List tự được khóa và không thể sửa từ cả hai
B. Mọi phần tử List bị chuyển thành immutable tự động
C. Java luôn tạo List mới khi copy tham chiếu của nó
D. Sửa List ở bản copy làm thay đổi dữ liệu bản gốc
Đáp án đúng: D

5. Trường `String title` bất biến của mẫu thường có thể xử lý thế nào?
A. Phải deep copy mỗi String để tránh cập nhật từ bản sao
B. Phải đặt String về null mỗi khi clone đối tượng
C. Phải đưa String vào registry trước khi trả về clone
D. Chia sẻ tham chiếu an toàn vì không thể sửa nội dung
Đáp án đúng: D

6. Trong deep copy của đồ thị object mutable, mục tiêu cốt lõi là gì?
A. Chỉ copy reference của node con rồi giữ nguyên object
B. Tạo bản độc lập cho các node cần tách trạng thái
C. Chuyển mọi node thành singleton trên heap JVM
D. Bỏ qua mọi node con có quan hệ với object gốc
Đáp án đúng: B

7. Hai field của mẫu cùng trỏ một node con, deep copy đúng thường giữ điều gì?
A. Hai field bản copy trỏ hai node mới không liên hệ nhau
B. Hai field bản copy luôn trỏ node con của bản gốc
C. Hai field bản copy cùng trỏ một node con mới duy nhất
D. Chỉ field thứ nhất được copy, field còn lại là null
Đáp án đúng: C

8. Khi deep copy đồ thị có chu trình A → B → A, kỹ thuật nào hữu ích?
A. Duyệt đệ quy không lưu trạng thái cho tới khi xong
B. Chỉ sao chép node có tên đứng trước trong bảng chữ cái
C. Đổi mọi reference thành chuỗi tên class khi copy
D. Lưu mapping object đã copy để tránh vòng lặp vô hạn
Đáp án đúng: D

9. Prototype Registry thường chịu trách nhiệm gì khi được yêu cầu một key?
A. Tìm mẫu đã đăng ký và tạo bản copy từ mẫu đó
B. Tạo class mới cho mỗi key bằng cách biên dịch runtime
C. Chỉ trả về cùng một object mẫu để mọi caller tự sửa
D. Giữ tất cả clone trong một transaction database chung
Đáp án đúng: A

10. Vì sao registry không nên trả thẳng prototype mutable cho client?
A. Mọi object trả về bị Java buộc thành immutable
B. Registry sẽ không thể lưu thêm bất kỳ key nào nữa
C. Client có thể sửa mẫu chung và làm ảnh hưởng lượt sau
D. Bộ nhớ JVM tự hủy toàn bộ mẫu sau mỗi lượt đọc
Đáp án đúng: C

11. Hợp đồng `copy()` của Prototype nên làm rõ điều gì?
A. Chỉ tên method gọi constructor của lớp Product
B. Chỉ số lượng method static có trên object nguồn
C. Phần nào được tách riêng và phần nào chia sẻ an toàn
D. Chỉ vị trí của prototype trong cấu trúc package
Đáp án đúng: C

12. Trong Java, `Object.clone()` mặc định có kiểu sao chép nào?
A. Sao chép nông các field, kể cả các reference
B. Tạo mới toàn bộ graph object theo deep copy
C. Chuyển mọi field instance thành static trong clone
D. Tạo đối tượng mới nhưng không chép field nào
Đáp án đúng: A

13. Vì sao `Cloneable` của Java không tự bảo đảm clone sâu?
A. Nó buộc mọi reference tự trở thành object bất biến
B. Nó chỉ là marker; quy tắc sao chép cần tự triển khai
C. Nó luôn tự tìm copy constructor của object con
D. Nó chỉ hoạt động với collection đã thread safe
Đáp án đúng: B

14. Nếu lớp dùng `super.clone()` mà không implements `Cloneable`, kết quả phổ biến là gì?
A. Ném `CloneNotSupportedException` khi gọi `clone()`
B. Tự động gọi public constructor rỗng của lớp gốc
C. Trả về cùng instance hiện tại mà không tạo bản mới
D. Tự chuyển class sang `Serializable` trước khi copy
Đáp án đúng: A

15. So với `clone()`, copy constructor cho phép làm điều gì rõ ràng?
A. Tự động tái sử dụng global singleton khi được gọi
B. Không cần xử lý mọi tham chiếu mutable bên trong
C. Không thể tạo được object của cùng một concrete class
D. Chọn quy tắc sao chép từng field qua constructor
Đáp án đúng: D

16. Với `Date` mutable chứa trong đối tượng, muốn bản copy độc lập cần làm gì?
A. Giữ nguyên reference Date của bản gốc trong cả hai
B. Chỉ đổi tên field Date khi gọi copy constructor
C. Đưa Date vào biến static để các bản copy dùng chung
D. Tạo một Date mới từ giá trị thời gian của bản gốc
Đáp án đúng: D

17. Khi sao chép entity để tạo entity nghiệp vụ hoàn toàn mới, phải xem xét điều gì?
A. Đặt lại identity và trạng thái vòng đời nếu miền yêu cầu
B. Giữ nguyên mọi primary key vì copy luôn là cùng entity
C. Xóa mọi field giá trị khác để tránh trùng dữ liệu
D. Đảm bảo clone tham chiếu tới cùng hàng DB ban đầu
Đáp án đúng: A

18. Với object giữ kết nối socket đang mở, phép copy cần chú ý gì?
A. Không sao chép mù quáng tài nguyên ngoài JVM đang sống
B. Sao chép tham chiếu socket là đủ để có hai kết nối độc lập
C. `Object.clone()` tự mở kết nối TCP mới khi sao chép
D. Chuyển socket thành chuỗi địa chỉ là deep copy hoàn chỉnh
Đáp án đúng: A

19. Kiểm thử nào giúp phát hiện lỗi chia sẻ tham chiếu mutable ngoài ý muốn?
A. So sánh tên class của bản gốc và bản sao trước khi sửa
B. Sửa nested object ở bản copy rồi kiểm tra bản gốc không đổi
C. Chỉ đo tốc độ copy hai object với cùng dữ liệu đầu vào
D. Chỉ kiểm tra hashCode khác nhau giữa bản gốc và bản sao
Đáp án đúng: B

20. Khi một cấu hình phức tạp được tạo mẫu trước, Prototype có lợi thế nào?
A. Buộc mỗi client gọi lại toàn bộ bước khởi tạo phức tạp
B. Bảo đảm mọi object copy phải dùng cùng identity gốc
C. Thay thế tất cả quy tắc validation của cấu hình
D. Tránh lặp lại chi phí khởi tạo cấu hình cho từng bản mới
Đáp án đúng: D

21. Khi nhiều thread dùng chung một prototype có thể sửa được, giải pháp nào an toàn hơn?
A. Cho phép một thread sửa mẫu trong lúc thread khác đọc
B. Đóng băng mẫu hoặc đồng bộ lúc lấy snapshot để copy
C. Dùng shallow copy rồi coi mọi mutable field đều thread safe
D. Thay mọi cơ chế đồng bộ bằng cách tăng số clone
Đáp án đúng: B

22. Đánh đổi phổ biến của deep copy so với shallow copy là gì?
A. Giảm chi phí vì tất cả reference được tái sử dụng
B. Tốn thêm CPU và bộ nhớ để tách các node mutable
C. Không tạo được bản copy có cùng giá trị với bản gốc
D. Buộc phải truy cập database cho mọi object con
Đáp án đúng: B

23. Prototype khác Builder ở cách tạo object như thế nào?
A. Chọn subclass bằng phương thức ảo của Creator
B. Bắt mọi sản phẩm được tạo bằng một singleton registry
C. Sao chép mẫu có sẵn thay vì cấu hình theo từng bước
D. Dùng một transaction chung để cấu hình các object
Đáp án đúng: C

24. Khi nhiều loại Prototype cùng thực hiện `copy()`, client có thể tránh phụ thuộc lớp cụ thể bằng gì?
A. Kiểm tra tên từng class rồi dùng constructor tương ứng
B. Ép mọi prototype thành cùng một kiểu product concrete
C. Gọi `copy()` qua interface chung của Prototype
D. Chỉ lưu một bản mẫu duy nhất cho mọi loại đối tượng
Đáp án đúng: C
