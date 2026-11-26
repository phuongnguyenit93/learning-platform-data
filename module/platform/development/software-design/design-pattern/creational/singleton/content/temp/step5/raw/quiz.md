1. Mục tiêu cốt lõi của mẫu Singleton là kiểm soát điều gì?
A. Quy trình lựa chọn subclass sản phẩm tại thời điểm chạy
B. Việc tạo bản sao đối tượng từ một prototype có sẵn
C. Thứ tự cấu hình nhiều tham số trước khi tạo đối tượng
D. Số instance của một lớp trong phạm vi quản lý xác định
Đáp án đúng: D

2. Vì sao constructor của Singleton thường được khai báo `private`?
A. Bảo đảm mọi field của instance đều có kiểu immutable
B. Cho phép subclass bên ngoài override constructor ảo
C. Hạn chế code bên ngoài tự gọi `new` để tạo instance
D. Tự động đăng ký instance vào dependency injection
Đáp án đúng: C

3. Phương thức `getInstance()` thường có nhiệm vụ gì?
A. Tạo instance mới cho mỗi lần gọi từ một client
B. Cung cấp điểm truy cập tới instance được kiểm soát
C. Sao chép trạng thái của instance ra object độc lập
D. Ghi mọi thay đổi instance vào repository của hệ thống
Đáp án đúng: B

4. Trong eager initialization, instance thường được tạo lúc nào?
A. Ở lần gọi đầu tiên tới một method nghiệp vụ
B. Sau khi thread đầu tiên hoàn thành tác vụ xử lý
C. Trong quá trình class được khởi tạo bởi JVM
D. Khi garbage collector chuẩn bị thu hồi vùng nhớ
Đáp án đúng: C

5. Nhược điểm của eager initialization với tài nguyên đắt đỏ là gì?
A. Làm mọi field mutable tự động trở thành thread safe
B. Buộc mọi caller phải tạo instance bằng reflection
C. Làm constructor public cho phép tạo vô hạn instance
D. Có thể khởi tạo cả khi ứng dụng chưa thực sự cần
Đáp án đúng: D

6. Đoạn lazy `if(instance==null) instance=new S()` không đồng bộ có rủi ro gì?
A. JVM tự ném exception khi hai thread cùng đọc null
B. Một thread sẽ tự khóa mọi method của class còn lại
C. Mọi lời gọi luôn trả về null khi hệ thống tải cao
D. Hai thread có thể cùng tạo các instance khác nhau
Đáp án đúng: D

7. Initialization-on-demand holder trong Java tận dụng tính chất nào?
A. Bảo đảm mutex của hệ điều hành luôn được giữ suốt đời
B. Khởi tạo class của JVM để tạo instance an toàn khi cần
C. Tự dùng một constructor public do compiler sinh ra
D. Tự viết instance ra disk để các JVM cùng truy cập
Đáp án đúng: B

8. Trong double-checked locking, vì sao field `instance` thường cần `volatile`?
A. Đảm bảo visibility và ngăn reorder gây thấy object chưa xong
B. Để JVM tự giải phóng instance giữa các lần gọi
C. Để field biến thành bất biến dù đối tượng vẫn mutable
D. Để thay thế hoàn toàn khóa ở nhánh khởi tạo null
Đáp án đúng: A

9. Đặt `synchronized` trên toàn bộ `getInstance()` có đánh đổi gì?
A. Bỏ qua đồng bộ trong đúng lần tạo instance đầu tiên
B. Cho phép mọi thread đồng thời dựng các instance khác
C. Bảo đảm các method nghiệp vụ trong instance tự an toàn
D. Dễ đúng nhưng chịu chi phí đồng bộ mỗi lần truy cập
Đáp án đúng: D

10. Một `enum Singleton { INSTANCE; }` trong Java nổi bật ở lợi ích nào?
A. Cho phép lazy khởi tạo lại mỗi lần gọi `values()`
B. Khởi tạo an toàn và hỗ trợ serialization giữ identity
C. Cho phép kế thừa từ một lớp concrete khác của ứng dụng
D. Tự bảo đảm mọi field mutable đều được đồng bộ
Đáp án đúng: B

11. Với Singleton thường implements `Serializable`, thao tác nào hay dùng để giữ identity khi đọc lại?
A. Override `finalize()` để chặn tạo object khi deserialize
B. Thêm `transient` vào mọi method của singleton
C. Cung cấp `readResolve()` trả về instance hiện có
D. Để `serialVersionUID` tự đóng vai trò registry
Đáp án đúng: C

12. Vì sao việc dùng reflection có thể phá Singleton dùng private constructor?
A. Reflection chỉ gọi được constructor public của tất cả lớp
B. Reflection tự tái sử dụng instance trong biến static
C. Reflection luôn bị cấm ở mọi dự án Java hiện đại
D. Reflection có thể vượt kiểm soát truy cập nếu được phép
Đáp án đúng: D

13. Một Singleton trong ứng dụng dùng nhiều classloader có giới hạn nào?
A. Mỗi classloader có thể có bản static singleton riêng
B. Mọi classloader bắt buộc chia sẻ đúng một field static
C. Mọi Singleton tự tồn tại chung ở tất cả JVM trên mạng
D. Một classloader chỉ được phép khởi tạo một lớp trong JVM
Đáp án đúng: A

14. Singleton có bảo đảm duy nhất một instance trên hai JVM khác nhau không?
A. Có; trường static được đồng bộ tự động qua mạng
B. Có; classloader luôn hoạt động trên toàn bộ cluster
C. Không; mỗi JVM có trạng thái static của riêng mình
D. Không; vì constructor private chỉ dùng được trong IDE
Đáp án đúng: C

15. Bean scope `singleton` mặc định của Spring thường có phạm vi nào?
A. Một instance duy nhất trên mọi process Java trong mạng
B. Một instance mỗi định nghĩa bean trong một Spring container
C. Một instance mới được tạo cho từng HTTP request
D. Một instance duy nhất cho mọi class cùng implements interface
Đáp án đúng: B

16. Thread-safe initialization của Singleton có đảm bảo method sửa `Map` bên trong an toàn không?
A. Không; state mutable vẫn cần quy tắc đồng bộ riêng
B. Có; field static làm mọi Map operation trở thành atomic
C. Có; constructor private tự khóa mọi method public
D. Không; vì instance được khởi tạo ở cùng một thread
Đáp án đúng: A

17. Vì sao dùng Singleton để giữ dữ liệu riêng của từng request dễ gây lỗi?
A. Nhiều request có thể dùng chung và ghi đè state của nhau
B. Mỗi request mặc định nhận một bản sao instance riêng
C. Singleton tự xóa mọi state ở cuối từng HTTP response
D. Đường dẫn API khác nhau luôn có classloader riêng
Đáp án đúng: A

18. Singleton bị gọi trực tiếp từ mã nghiệp vụ làm việc unit test khó hơn ở điểm nào?
A. Mọi unit test phải chạy trên một JVM riêng theo quy định
B. Phụ thuộc toàn cục khó thay bằng fake và reset trạng thái
C. Class dùng Singleton không thể biên dịch trong test
D. Mọi phương thức truy cập Singleton đều không thể mock
Đáp án đúng: B

19. Dependency injection có thể thay thế Singleton viết tay bằng cách nào?
A. Container tạo một instance mới mỗi lần gọi business method
B. Container quản lý một instance và truyền qua interface
C. Container buộc dùng constructor static private của mọi lớp
D. Container tự làm cho mọi service stateful trở thành stateless
Đáp án đúng: B

20. Singleton nắm một tài nguyên có thể đóng như client mạng cần chú ý gì?
A. Bỏ qua cleanup vì instance tồn tại suốt quá trình chạy
B. Tạo client mạng mới ở mỗi lần gọi `getInstance()`
C. Quản lý vòng đời và đóng tài nguyên khi ứng dụng dừng
D. Để garbage collector xác nhận giao dịch mạng đã xong
Đáp án đúng: C

21. Vì sao một Singleton `Connection` duy nhất thường không thay connection pool?
A. Một connection không đáp ứng tốt tải đồng thời và hồi phục
B. Một connection luôn hỗ trợ vô hạn query song song an toàn
C. Pooling bắt buộc tạo database khác cho mỗi thread gọi
D. Singleton đảm bảo mỗi transaction tự có kết nối độc lập
Đáp án đúng: A

22. Một enum Singleton có thể kế thừa class nghiệp vụ khác không?
A. Có; enum tự động kế thừa từ mọi superclass
B. Có; chỉ cần thêm `extends` vào khai báo enum
C. Không; vì enum không thể implements interface Java
D. Không; enum đã kế thừa `java.lang.Enum`
Đáp án đúng: D

23. So với lớp chỉ có method `static`, Singleton cho phép điều gì thuận lợi hơn?
A. Buộc các method static hỗ trợ override đa hình trực tiếp
B. Tạo object mới mỗi lần truy cập mà vẫn gọi là Singleton
C. Cung cấp object có thể triển khai interface và được truyền đi
D. Bảo đảm không tồn tại bất kỳ mutable state trong object
Đáp án đúng: C

24. Khi nào nên tránh áp dụng Singleton cho một chức năng?
A. Khi trạng thái riêng từng user cần được cô lập theo phiên
B. Khi dịch vụ hoàn toàn stateless được container quản lý
C. Khi cấu hình bất biến dùng chung trong một tiến trình
D. Khi cần một điểm truy cập tới bộ mô tả chỉ đọc
Đáp án đúng: A
