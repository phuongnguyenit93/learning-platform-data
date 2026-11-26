Phân tích closed-world của Native Image chủ yếu xác định điều gì?
A. Các lớp và method đi tới từ entry point đã biết.
B. Mọi lớp có mặt trong tất cả JAR của classpath ứng dụng.
C. Mọi method có thể được gọi qua reflection ở runtime.
D. Toàn bộ resource trong mọi thư mục của ứng dụng.
Đáp án đúng: A

Vì sao Class.forName bằng tên lấy từ cấu hình có thể lỗi trong native executable?
A. Native Image không hỗ trợ khởi tạo lớp khi chương trình chạy.
B. Tên lớp trong cấu hình luôn bị xóa khi đóng gói executable.
C. Phân tích tĩnh không tự nhận ra mọi lớp được nạp động.
D. Heap của native executable không lưu được metadata của lớp.
Đáp án đúng: C

Tracing Agent của GraalVM thường được dùng để hỗ trợ công việc nào?
A. Tự động chuyển mọi lời gọi reflection thành lời gọi tĩnh.
B. Đo thời gian startup để tự chọn garbage collector phù hợp.
C. Phát hiện và sửa các lỗi JNI trong thư viện native.
D. Ghi nhận truy cập động trong workload thử nghiệm.
Đáp án đúng: D

Reflection metadata cần khai báo những thông tin nào khi ứng dụng truy cập động?
A. Các lớp cùng constructor, method hoặc field cần truy cập.
B. Toàn bộ biến môi trường sẽ được đọc khi process khởi động.
C. Mọi package trong classpath và thứ tự nạp từng JAR.
D. Tất cả file cấu hình được lưu ngoài thư mục executable.
Đáp án đúng: A

Khi tạo dynamic proxy trong Native Image, metadata thường cần mô tả điều gì?
A. Các interface được kết hợp để tạo proxy lúc chạy.
B. Mọi implementation của interface trong toàn bộ classpath.
C. Các địa chỉ IP mà proxy có thể gọi khi ứng dụng chạy.
D. Những thread sẽ thực thi từng method của proxy.
Đáp án đúng: A

Ứng dụng đọc template từ classpath nhưng native executable báo thiếu file; cần xử lý thế nào?
A. Tăng heap size để resource được giữ trong bộ nhớ.
B. Đưa resource cần dùng vào cấu hình image.
C. Bật JIT compiler để classloader tìm lại resource.
D. Thêm mọi thư mục trong máy build vào PATH.
Đáp án đúng: B

Vì sao ServiceLoader có thể không tìm thấy provider trong native executable?
A. Native Image không hỗ trợ interface có nhiều implementation.
B. Provider luôn phải được tạo bằng JNI thay vì Java.
C. Provider phải được tạo qua reflection thay vì ServiceLoader.
D. Giữ service descriptor cùng provider trong image.
Đáp án đúng: D

Rủi ro chính khi class được khởi tạo ở build time là gì?
A. Static value có thể mang môi trường build sang runtime.
B. Class đó sẽ luôn được biên dịch lại mỗi khi process khởi động.
C. Mọi method của class sẽ bị loại khỏi executable.
D. JVM sẽ tự động nạp lại class từ file JAR gốc.
Đáp án đúng: A

Khi static initializer cần đọc secret riêng của production, nên chọn cách nào?
A. Đưa secret vào static field trong lúc build executable.
B. Khởi tạo class lúc runtime sau khi nạp cấu hình.
C. Lưu secret trong tên class để Native Image giữ lại.
D. Dùng tracing agent để ghi secret vào reflection metadata.
Đáp án đúng: B

JNI metadata trong Native Image chủ yếu phục vụ tình huống nào?
A. Cho phép Java gọi mọi method private mà không cần reflection.
B. Tự động biên dịch thư viện C thành bytecode Java.
C. Khai báo thành phần Java mà native code gọi qua JNI.
D. Đóng gói mọi thư viện hệ điều hành vào Java heap.
Đáp án đúng: C

Điều gì cần được kiểm tra khi native executable nạp shared library?
A. Thư viện có cùng phiên bản JDK với máy build hay không.
B. Tên package Java có trùng với tên file thư viện hay không.
C. File thư viện có nằm trong Java classpath hay không.
D. Đúng OS, kiến trúc và ABI của môi trường đích.
Đáp án đúng: D

Native thread gọi callback vào Java qua JNI cần chú ý điều gì?
A. Chuyển thread thành daemon trước khi gọi bất kỳ method nào.
B. Attach thread theo JNI trước khi gọi vào Java.
C. Gọi System.gc() để đồng bộ trạng thái thread với runtime.
D. Tạo một Java classloader mới cho mỗi lần callback.
Đáp án đúng: B

Vì sao plugin JAR được tải tùy ý sau khi native executable khởi động là vấn đề?
A. Closed-world không biết trước lớp plugin mới.
B. Native Image chỉ cho phép một JAR trong classpath.
C. Plugin không thể gọi method của interface Java.
D. Executable không thể đọc file từ filesystem sau khi chạy.
Đáp án đúng: A

Ứng dụng dùng Java serialization cho lớp chỉ được tham chiếu động; cần bảo đảm điều gì?
A. Mọi object được serialize phải lưu trên filesystem cục bộ.
B. Giữ lớp và metadata cần cho serialization.
C. Tất cả trường của object phải chuyển thành biến static.
D. Serialization phải được thay bằng JNI trong mọi trường hợp.
Đáp án đúng: B

ResourceBundle chỉ tải được locale mặc định trong native executable; cần kiểm tra gì?
A. Heap tối đa có đủ lớn cho mọi bản dịch hay không.
B. Các locale khác có được bật trong hệ điều hành hay không.
C. Bundle và locale cần dùng phải có trong image.
D. Ứng dụng có chạy bằng virtual thread hay không.
Đáp án đúng: C

Spring AOT Runtime Hints thường được dùng để làm gì?
A. Tăng số worker thread được tạo khi server khởi động.
B. Đăng ký trước reflection, proxy và resource.
C. Chuyển mọi bean thành lớp JNI để gọi nhanh hơn.
D. Thay thế toàn bộ dependency injection bằng biến môi trường.
Đáp án đúng: B

Khi nâng phiên bản thư viện có reachability metadata, nên xác minh điều gì?
A. Tên artifact có giữ nguyên giữa các lần phát hành.
B. Metadata phải khớp phiên bản dependency đang dùng.
C. Số lượng class trong JAR có bằng phiên bản trước.
D. Thư viện có được đóng gói trong executable của máy build.
Đáp án đúng: B

Ứng dụng dựa vào classpath scanning để tìm plugin; hướng xử lý phù hợp cho Native Image là gì?
A. Tăng thời gian startup để scanner có thêm thời gian chạy.
B. Đưa toàn bộ thư mục home của người dùng vào image.
C. Đăng ký plugin bằng thông tin xác định lúc build.
D. Bật JIT để scanner có thể định nghĩa class mới.
Đáp án đúng: C

Static initializer mở kết nối database trong lúc native-image build; nên xử lý thế nào?
A. Tăng timeout database để build chờ kết nối lâu hơn.
B. Tắt kiểm tra reachability cho toàn bộ package database.
C. Lưu connection object vào image heap để dùng lại production.
D. Chuyển việc kết nối sang runtime initialization phù hợp.
Đáp án đúng: D

Native executable thường bị ràng buộc bởi thuộc tính nào của môi trường build?
A. Tên người dùng và thư mục home của người biên dịch.
B. Phiên bản trình duyệt được cài trên máy build.
C. OS và kiến trúc CPU mà binary được biên dịch cho.
D. Tên repository Git chứa mã nguồn ứng dụng.
Đáp án đúng: C

Vì sao binary build trên glibc có thể không chạy trong Alpine Linux?
A. Alpine không hỗ trợ chạy bất kỳ executable native nào.
B. Alpine chỉ chạy ứng dụng Java dưới dạng file JAR.
C. Binary glibc có thể cần thư viện glibc trên host.
D. Native Image luôn yêu cầu hệ điều hành có systemd.
Đáp án đúng: C

Khi phát hành native executable cho ARM64 và x86_64, cách làm nào phù hợp?
A. Build và kiểm thử riêng cho từng kiến trúc đích.
B. Đổi tên cùng một binary để tạo hai artifact khác nhau.
C. Dùng một executable x86_64 vì JVM tự chuyển mã khi chạy.
D. Chỉ đổi biến môi trường để binary nhận kiến trúc mới.
Đáp án đúng: A

Native Image build trong CI bị hệ điều hành kill vì thiếu RAM; nên làm gì trước?
A. Giảm heap runtime của ứng dụng trong production.
B. Tăng số worker thread của ứng dụng được biên dịch.
C. Bật thêm resource scanning để giảm số class được phân tích.
D. Cấp đủ RAM cho native compilation trong CI.
Đáp án đúng: D

Profile-Guided Optimization có hiệu quả nhất khi profile được thu thập ra sao?
A. Chỉ chạy một lần khởi động rỗng không có request.
B. Lấy từ một binary khác dù code và dependency khác biệt.
C. Thu profile từ workload đại diện cho production.
D. Tạo thủ công bằng cách liệt kê tên các method trong source.
Đáp án đúng: C

Khác biệt nào thường thấy giữa startup và throughput dài hạn của Native Image so với JVM?
A. Native Image luôn có throughput cao hơn sau mọi thời gian warm-up.
B. JVM không thể tối ưu code sau khi ứng dụng đã khởi động.
C. Native Image thường khởi động nhanh; JVM JIT tối ưu khi chạy lâu.
D. Hai runtime luôn có cùng startup và throughput nếu dùng cùng heap.
Đáp án đúng: C

RSS của native executable cao hơn heap được báo cáo; nên xem xét điều gì?
A. Heap không gồm stack, code và native allocation.
B. Chỉ số heap đã tính cả mọi vùng memory của tiến trình.
C. RSS chỉ chứa file JAR được giữ trong Java classpath.
D. Mọi chênh lệch đều do filesystem page cache của host.
Đáp án đúng: A

Vì sao cần đo native memory khi đánh giá mức tiêu thụ bộ nhớ?
A. Vì heap usage phản ánh đầy đủ cả memory của thư viện C.
B. Thread stack và native allocation nằm ngoài heap.
C. Vì RSS chỉ tăng khi garbage collector chạy full collection.
D. Vì native executable không có vùng nhớ dành cho object.
Đáp án đúng: B

Khi cần phân tích stack trace của native crash, artifact nào nên được giữ?
A. Chỉ file JAR nguồn và ảnh container cuối cùng.
B. Log access của reverse proxy trước thời điểm crash.
C. Giữ binary, symbols và core dump khớp phiên bản.
D. File cấu hình heap size và biến môi trường runtime.
Đáp án đúng: C

Vì sao nên chạy integration test trên native executable thực tế?
A. Để thay thế toàn bộ unit test chạy trên JVM.
B. Để tự động sinh profile PGO cho mọi workload production.
C. Để bảo đảm executable chạy được trên mọi hệ điều hành.
D. Xác nhận reflection và resource hoạt động trong binary.
Đáp án đúng: D

Native executable gọi thư viện JNI nhưng container runtime báo thiếu shared object; cần kiểm tra gì?
A. Runtime image có chứa thư viện và loader path phù hợp.
B. Java heap có đủ chỗ lưu toàn bộ file thư viện hay không.
C. Reflection metadata có liệt kê tên mọi package JNI hay không.
D. JAR ứng dụng có được thêm vào biến CLASSPATH hay chưa.
Đáp án đúng: A

Ứng dụng native kết nối HTTPS thất bại trong container tối giản; nên kiểm tra gì?
A. Số worker thread tối đa của HTTP client có đủ cho tải không?
B. Trust store và CA certificate có trong runtime image.
C. PGO profile có chứa hostname của các đối tác hay không?
D. Heap dump có lưu certificate chain từ lần gọi trước không?
Đáp án đúng: B

Ứng dụng native định dạng ngày giờ khác JVM khi chạy trong container; cần kiểm tra gì?
A. Kích thước code cache của executable có đủ lớn không.
B. Số lượng proxy interface đã khai báo trong metadata.
C. Native thread có được attach vào runtime đúng cách không.
D. Timezone, locale và dữ liệu vùng trong runtime image.
Đáp án đúng: D

Readiness probe của Kubernetes thất bại ngay sau khi native process khởi động; nên xử lý thế nào?
A. Tăng liveness failure threshold để process không bị kill.
B. Xóa health endpoint khỏi cấu hình của ứng dụng.
C. Đặt readiness thành thành công ngay khi tạo process.
D. Chỉ báo ready khi các dependency cần thiết đã sẵn sàng.
Đáp án đúng: D

Khi quyết định chuyển workload Java sang Native Image, cách đánh giá nào phù hợp?
A. Chỉ so kích thước binary với file JAR sau khi đóng gói.
B. Đo startup, throughput, memory và chi phí build.
C. Chỉ đo heap usage khi ứng dụng chưa nhận request.
D. Chọn Native Image nếu số class trong ứng dụng ít.
Đáp án đúng: B

Một ứng dụng cần runtime compilation mã do người dùng cung cấp; cần cân nhắc điều gì?
A. Có thể giữ phần này trên JVM hoặc thiết kế lại.
B. Chỉ cần khai báo resource metadata cho mã người dùng.
C. Native Image sẽ tự biên dịch mọi mã mới thành machine code.
D. Tăng heap size sẽ cho phép thêm class tùy ý vào image.
Đáp án đúng: A

Khi native executable crash trong code C mà không có Java exception, nên thu thập gì?
A. Chỉ heap histogram từ một lần chạy thành công trước đó.
B. Danh sách dependency Maven không kèm phiên bản binary.
C. Ảnh dashboard CPU của node tại thời điểm gần nhất.
D. Core dump, native stack và symbols đúng phiên bản.
Đáp án đúng: D
