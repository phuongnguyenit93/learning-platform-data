Câu 1: Vì sao máy dùng để biên dịch mã Java cần có JDK?
A. JDK có javac để biên dịch mã Java thành bytecode
B. JDK thay thế Git để quản lý lịch sử thay đổi mã
C. JDK tự cài mọi dependency mà dự án yêu cầu
D. JDK tự chạy tất cả bài test khi mở terminal
Đáp án đúng: A

Câu 2: Lệnh nào kiểm tra phiên bản trình biên dịch Java đang được sử dụng?
A. java -version
B. javadoc -version
C. javac -version
D. jar --version
Đáp án đúng: C

Câu 3: JAVA_HOME trong môi trường build Java thường dùng để làm gì?
A. Chỉ tới thư mục source mà trình biên dịch phải đọc
B. Chỉ tới thư mục artifact được upload lên CI
C. Chỉ tới thư mục cài JDK mà công cụ sẽ dùng
D. Chỉ tới thư mục cache Git của repository hiện tại
Đáp án đúng: C

Câu 4: Vì sao dự án nên dùng Maven Wrapper hoặc Gradle Wrapper?
A. Tự đồng bộ mọi biến môi trường giữa các máy
B. Dùng phiên bản công cụ build đã chọn cho dự án
C. Tự nâng tất cả thư viện lên bản mới nhất
D. Tự thay thế compiler Java bằng compiler Kotlin
Đáp án đúng: B

Câu 5: Khi chạy lệnh với đường dẫn tương đối, cơ sở để phân giải đường dẫn là gì?
A. Thư mục làm việc hiện tại của terminal
B. Thư mục cài đặt JDK mặc định của máy chủ
C. Thư mục chứa repository Git đầu tiên trên ổ đĩa
D. Thư mục chứa dependency cache của build tool
Đáp án đúng: A

Câu 6: Lệnh git status có vai trò chính nào trong workflow?
A. Xác định commit nào có hiệu năng chạy nhanh nhất
B. Đẩy toàn bộ commit cục bộ lên remote mặc định
C. Cho biết nhánh, file sửa và trạng thái stage
D. Gộp các nhánh thay đổi thành commit duy nhất
Đáp án đúng: C

Câu 7: Muốn xem phần thay đổi đã được git add đưa vào index, dùng lệnh nào?
A. git diff --check
B. git diff --stat
C. git diff --name-only
D. git diff --staged
Đáp án đúng: D

Câu 8: Muốn bỏ stage một file mà vẫn giữ nội dung sửa trong working tree, làm gì?
A. Dùng git restore --staged cho file cần bỏ stage
B. Dùng git restore --worktree để bỏ stage cho file
C. Dùng git clean -f để bỏ stage cho file
D. Dùng git reset --hard để bỏ stage cho file
Đáp án đúng: A

Câu 9: So với git pull, git fetch khác gì khi lấy cập nhật remote?
A. Tự động merge remote vào nhánh hiện tại ngay khi hoàn thành
B. Tải remote refs mà chưa merge vào nhánh hiện tại
C. Xóa toàn bộ commit chưa đẩy khỏi nhánh hiện tại
D. Ghi đè file đã sửa trong working tree ở mỗi lần fetch
Đáp án đúng: B

Câu 10: Khi merge có conflict, bước nào giúp giải quyết đúng?
A. Xem hai phía, hợp nhất nội dung rồi đánh dấu resolved
B. Chọn tất cả thay đổi từ nhánh mình bất kể nghiệp vụ
C. Xóa các marker conflict rồi commit mà không build lại
D. Reset cả repository về commit cũ trước khi review
Đáp án đúng: A

Câu 11: Khi cần hoàn tác một commit đã chia sẻ, cách nào thường an toàn?
A. Dùng git reset --hard rồi force push mọi nhánh liên quan
B. Tạo commit đảo ngược bằng git revert trên nhánh chung
C. Xóa thư mục .git để bỏ commit khỏi lịch sử được chia sẻ
D. Dùng git clean -fd để loại commit khỏi remote repository
Đáp án đúng: B

Câu 12: Vì sao thêm mẫu vào .gitignore chưa làm Git ngừng theo dõi file đã commit?
A. Ignore không bỏ theo dõi các file đã được Git track
B. Git chỉ đọc .gitignore ở root filesystem của máy
C. Git phải chạy git fetch mới nhận mọi thay đổi ignore
D. Git chỉ hỗ trợ ignore file có phần mở rộng .java
Đáp án đúng: A

Câu 13: Trong Maven, gọi mvn verify thường nhằm mục đích gì?
A. Thực hiện các phase build đến bước xác minh
B. Chỉ xóa toàn bộ thư mục target mà không chạy test
C. Chỉ tải dependency mà không chạy các phase build
D. Chỉ tạo Git tag cho artifact vừa đóng gói
Đáp án đúng: A

Câu 14: Dependency khai báo scope test trong Maven thường xuất hiện ở đâu?
A. Classpath runtime production mặc định của mọi module
B. Trong classpath biên dịch và chạy test của module
C. Classpath của plugin Maven bất kể module phụ thuộc
D. Classpath biên dịch production nhưng không có test
Đáp án đúng: B

Câu 15: Vai trò của ./gradlew trong repository Gradle là gì?
A. Khởi chạy mọi service Java trong IDE của lập trình viên
B. Khởi chạy Git hook ở mọi commit trong repository
C. Khởi chạy build bằng bản Gradle được wrapper chỉ định
D. Khởi chạy compiler JVM không cần đọc build.gradle
Đáp án đúng: C

Câu 16: Khi build cùng commit nhưng kết quả lệch giữa máy và CI, nên đối chiếu gì?
A. Theme IDE, font terminal và tỷ lệ zoom của cửa sổ
B. Số file README, độ dài tên nhánh và tên user
C. Màu syntax highlight và bộ icon đang được dùng
D. So sánh JDK, dependency và cấu hình build
Đáp án đúng: D

Câu 17: Để phát hiện dependency nào đưa một thư viện vào Maven project, nên dùng gì?
A. mvn clean để xem cây phụ thuộc được phân giải
B. mvn dependency:tree để xem cây phụ thuộc
C. mvn help:effective-pom để xóa thư viện không dùng
D. mvn test để đổi phiên bản thư viện tự động
Đáp án đúng: B

Câu 18: IDE báo lỗi nhưng build dòng lệnh thành công, bước kiểm tra hợp lý là gì?
A. Đổi tên tất cả package Java rồi build lại
B. Xóa toàn bộ unit test để đồng bộ trạng thái IDE
C. Kiểm tra SDK, module và index/cache của IDE
D. Chỉnh độ phân giải màn hình rồi tải lại dự án
Đáp án đúng: C

Câu 19: Vì sao refactor Rename trong IDE tốt hơn thay text đơn thuần?
A. Có thể cập nhật tham chiếu theo cấu trúc mã và scope
B. Luôn tự đổi toàn bộ tên cột trong cơ sở dữ liệu đang chạy
C. Luôn tự thêm test mới cho mọi phương thức đã đổi tên
D. Luôn tự cập nhật những service triển khai ở production
Đáp án đúng: A

Câu 20: Khi đọc dự án Java lạ, chức năng Find Usages giúp gì?
A. Tìm tất cả nhánh Git có commit của tác giả hiện tại
B. Tìm các thread JVM có thời gian CPU cao nhất
C. Tìm mọi cổng mạng mà ứng dụng đang lắng nghe
D. Tìm nơi trong mã đang tham chiếu tới symbol
Đáp án đúng: D

Câu 21: Trong debugger, Step Over có tác dụng gì?
A. Đi vào thân phương thức được gọi trên dòng hiện tại
B. Chạy thẳng tới điểm dừng tiếp theo không xét dòng hiện tại
C. Khởi động lại JVM rồi tiếp tục từ đầu phương thức
D. Thực hiện lời gọi trên dòng hiện tại mà không đi vào hàm
Đáp án đúng: D

Câu 22: Trong debugger, conditional breakpoint hữu ích khi nào?
A. Chỉ tạm dừng mỗi lần source file được biên dịch
B. Chỉ tạm dừng sau khi tất cả thread đã kết thúc
C. Chỉ dừng nếu biểu thức điều kiện trả true
D. Chỉ tạm dừng khi ứng dụng ghi artifact ra disk
Đáp án đúng: C

Câu 23: Khi exception bị bắt ở tầng cao và khó tìm nguồn, nên sử dụng gì?
A. Watch expression để đổi kiểu của exception
B. Heap histogram để tìm nơi phát sinh exception
C. Đặt exception breakpoint tại thời điểm phát sinh
D. Code formatter để tự loại ngoại lệ đã được ném
Đáp án đúng: C

Câu 24: Khi dừng debugger ở đoạn lỗi, call stack cho biết điều gì?
A. Toàn bộ lịch sử commit trước thời điểm chạy
B. Tất cả object đã được garbage collector thu hồi
C. Mọi thread từng chạy từ lúc tiến trình khởi động
D. Các lời gọi đang hoạt động dẫn tới điểm dừng
Đáp án đúng: D

Câu 25: Ứng dụng Java bị treo do chờ lock, bằng chứng ban đầu nào hữu ích?
A. Heap dump để xem các object lớn nhất trong heap
B. Thread dump để xem trạng thái thread và monitor
C. Maven dependency tree để xem các artifact được tải
D. Báo cáo coverage để xem các dòng test không chạy
Đáp án đúng: B

Câu 26: Ứng dụng Java tăng heap liên tục, snapshot nào giúp kiểm tra giữ tham chiếu?
A. Thread dump để kiểm tra toàn bộ classloader đã tải
B. Git reflog để kiểm tra quá trình cấp phát object
C. Compilation log để xác nhận các object còn sống
D. Heap dump để xem object và đường giữ tham chiếu
Đáp án đúng: D

Câu 27: Trong quy trình kiểm tra mã, formatter và static analyzer khác nhau thế nào?
A. Formatter kiểm tra race condition, analyzer căn lề mã
B. Formatter thay toàn bộ test, analyzer chạy tích hợp test
C. Formatter sửa SQL migration, analyzer xác nhận backup
D. Formatter chỉnh kiểu trình bày, analyzer báo mẫu lỗi
Đáp án đúng: D

Câu 28: Trước khi gửi pull request có refactor Java, bộ kiểm tra nào phù hợp?
A. Chỉ kiểm tra code compile trong IDE rồi bỏ qua CI
B. Chạy build, test và linter; rà soát diff
C. Chỉ xem Git status và bỏ qua mọi thay đổi hành vi
D. Chỉ chạy formatter rồi coi refactor không cần test
Đáp án đúng: B
