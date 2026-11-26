Câu 1. Template Method đặt phần nào của thuật toán vào lớp cơ sở?
A. Chỉ dữ liệu cấu hình riêng của từng lớp con
B. Chỉ tên các phương thức không có triển khai
C. Chỉ kết quả cuối do subclass cung cấp
D. Trình tự các bước chung của thuật toán
Đáp án đúng: D

Câu 2. Trong Template Method, hook khác phương thức abstract bắt buộc ở điểm nào?
A. Hook chỉ được khai báo trong interface Java
B. Hook có thể có mặc định, không buộc override
C. Hook bắt buộc phải được override ở mọi subclass
D. Hook tự động chạy riêng trước constructor
Đáp án đúng: B

Câu 3. Một bước bắt buộc mỗi định dạng xuất phải tự triển khai nên được khai báo thế nào?
A. Khai báo abstract method được template gọi
B. Khai báo private method cố định trong lớp cha
C. Khai báo final static method trong lớp cha
D. Khai báo constructor rỗng ở lớp con
Đáp án đúng: A

Câu 4. Muốn lớp con không thay đổi thứ tự kiểm tra và ghi tệp, nên thiết kế phương thức template ra sao?
A. Cho mọi lớp con override toàn bộ template
B. Khai báo template final để cố định thứ tự
C. Để subclass gọi bước kiểm tra sau khi ghi
D. Chỉ truyền template method qua lambda bên ngoài
Đáp án đúng: B

Câu 5. Một bước ghi log tùy chọn không phải subclass nào cũng cần. Thiết kế nào phù hợp?
A. Khai báo abstract method buộc mọi lớp con viết lại
B. Chuyển bước log thành constructor riêng cho từng class
C. Tạo hook mặc định rỗng cho lớp con chọn override
D. Để lớp con sửa trực tiếp body của template method
Đáp án đúng: C

Câu 6. Ba biến thể import dữ liệu đều phải validate trước khi save. Nên đặt validate ở đâu?
A. Trong template chung trước bước lưu dữ liệu
B. Chỉ trong subclass xuất hiện đầu tiên trong dự án
C. Trong từng subclass để tự chọn thứ tự thực thi
D. Trong code gọi mỗi subclass trước khi khởi tạo
Đáp án đúng: A

Câu 7. Một subclass ghi biến mutable dùng chung trong xử lý nhiều request. Rủi ro đặc biệt nào xuất hiện?
A. Template Method tự sinh khóa thread-safe cho subclass
B. Phương thức abstract luôn chạy trên một thread riêng
C. Mọi field của base class trở thành immutable khi gọi
D. Các lượt chạy song song có thể tranh chấp state
Đáp án đúng: D

Câu 8. Pipeline gồm mở tài nguyên, xử lý và đóng; template nên tổ chức cleanup như thế nào?
A. Để lớp con tự nhớ đóng ở mỗi nhánh kết thúc
B. Chỉ đóng tài nguyên khi xử lý hoàn tất thành công
C. Dùng finally để dọn tài nguyên cả khi lỗi
D. Chuyển cleanup ra bên ngoài nhưng không ràng buộc
Đáp án đúng: C

Câu 9. Khi bước tùy biến ném exception, cách nào giúp lớp cơ sở giữ chính sách lỗi nhất quán?
A. Template bao việc gọi bước trong xử lý lỗi chung
B. Lớp con tự quyết định mọi lỗi của các bước chung
C. Bỏ mọi thông tin exception trước khi chuyển lên
D. Gọi lại constructor để đặt lại toàn bộ trạng thái
Đáp án đúng: A

Câu 10. Để thêm biến thể xuất dữ liệu trong Template Method, cách mở rộng thông thường là gì?
A. Sửa toàn bộ logic template ở lớp cơ sở
B. Đổi tên các hook đang được lớp con sử dụng
C. Dùng if trong base class để nhận từng loại định dạng
D. Tạo subclass mới triển khai các bước biến đổi
Đáp án đúng: D

Câu 11. Điểm khác biệt chính giữa Strategy và Template Method trong cấu trúc mở rộng là gì?
A. Strategy luôn buộc subclass kế thừa base template
B. Template dùng kế thừa, Strategy thiên về composition
C. Template luôn cho đổi thuật toán bằng lambda runtime
D. Strategy chỉ dùng cho các thuật toán không có trạng thái
Đáp án đúng: B

Câu 12. Vì sao không nên gọi phương thức override từ constructor của lớp cơ sở?
A. Lớp con có thể chưa khởi tạo đủ trạng thái của mình
B. Java buộc các override method luôn ném exception
C. Các method override không bao giờ được virtual dispatch
D. Constructor luôn chạy sau mọi phương thức của lớp con
Đáp án đúng: A

Câu 13. Khi subclass không được bỏ qua bước kiểm tra quyền truy cập, nên đặt bước đó ở đâu?
A. Trong một hook tùy chọn có mặc định rỗng
B. Trong method public mà mọi subclass override
C. Trong template cố định trước các bước tùy biến
D. Trong riêng từng subclass để tối ưu theo định dạng
Đáp án đúng: C

Câu 14. Lợi thế đặc trưng của abstract class với Template Method trong Java là gì?
A. Có thể kế thừa nhiều lớp cơ sở đồng thời
B. Dùng chung state, code và protected hooks
C. Tự động thay implementation mà không cần subclass
D. Bắt mọi method đều public như một interface
Đáp án đúng: B

Câu 15. Một họ thuật toán thay đổi cả trình tự bước theo từng lần gọi. Khi nào Template Method kém phù hợp?
A. Khi mọi bước đều có một thứ tự cố định bất biến
B. Khi chỉ một bước có triển khai khác ở lớp con
C. Khi tất cả biến thể dùng chung xử lý lỗi
D. Khi cần đổi cả luồng qua composition lúc chạy
Đáp án đúng: D

Câu 16. Muốn unit test thứ tự gọi các bước trong template, phương pháp nào phù hợp?
A. Chỉ kiểm tra lớp base có từ khóa abstract
B. Tạo subclass test ghi lại trình tự các bước
C. Chỉ chạy constructor của lớp base và xem exception
D. Chỉ so độ dài mã nguồn giữa base và subclass
Đáp án đúng: B

Câu 17. Một thuật toán cần luôn commit sau khi validate và persist thành công. Thiết kế nào giữ invariant?
A. Để template kiểm soát commit sau các bước bắt buộc
B. Cho subclass override mọi bước gồm cả thứ tự commit
C. Cho subclass tự xóa validate khi giảm thời gian chạy
D. Đặt commit trong một hook không cần định nghĩa
Đáp án đúng: A

Câu 18. Khi thêm hook cho phép subclass bỏ qua bước tùy chọn, điều gì cần mô tả rõ?
A. Chỉ tên file chứa hook trong source repository
B. Chỉ số lượng các lớp đã kế thừa từ base
C. Mô tả điều kiện override và tác động sau đó
D. Cách chia tệp Java thành các package nhỏ hơn
Đáp án đúng: C

Câu 19. Một bước của template bắt buộc mọi subclass cung cấp để tạo output. Hình thức nào rõ nhất?
A. Hook có implementation rỗng để không có lỗi
B. Method final trả về null trong mọi trường hợp
C. Method private của base luôn ném lỗi khi chạy
D. Khai báo abstract method với hợp đồng rõ
Đáp án đúng: D

Câu 20. Vì sao việc thêm quá nhiều hook vào lớp cơ sở có thể làm thiết kế khó bảo trì?
A. Hook mặc định tự làm tăng số database connection
B. Hook biến mọi method thành static trong JVM
C. Hook có thể gây nhiều tổ hợp override khó hiểu
D. Hook làm mất khả năng sử dụng các lớp con
Đáp án đúng: C

Câu 21. Subclass muốn bỏ qua bước audit bắt buộc để chạy nhanh hơn. Cách bảo vệ nào thích hợp?
A. Chuyển audit thành comment trong subclass nhanh
B. Giữ audit trong template final, không để hook bỏ qua
C. Cho phép override template nếu subclass là final
D. Chỉ dựa vào hướng dẫn lập trình khi triển khai
Đáp án đúng: B

Câu 22. Khi lớp cơ sở expose quá nhiều protected field, rủi ro nào tăng?
A. Subclass tự động bị ép chuyển sang composition
B. Hook không thể truy cập bất kỳ phương thức abstract
C. Template method buộc phải thay thành static method
D. Subclass phụ thuộc mạnh vào state nội bộ base
Đáp án đúng: D

Câu 23. Muốn thay một bước xử lý khi đang chạy thay vì tạo subclass mới, lựa chọn nào có thể phù hợp hơn?
A. Dùng một abstract method chỉ được override lúc compile
B. Dùng final method cố định từng bước trong base
C. Tiêm Strategy cho bước biến đổi cần thay thế
D. Bỏ interface và chuyển mọi bước thành constructor
Đáp án đúng: C

Câu 24. Nhiều định dạng báo cáo dùng chung đọc dữ liệu, validate và xuất kết quả; đâu là vị trí hợp lý cho biến thể?
A. Template giữ trình tự, subclass lo bước xuất
B. Mỗi subclass tự sao chép toàn bộ luồng từ đầu
C. Context bên ngoài viết nhánh xử lý cho mọi định dạng
D. Base class tự so tên subclass rồi chọn thuật toán
Đáp án đúng: A
