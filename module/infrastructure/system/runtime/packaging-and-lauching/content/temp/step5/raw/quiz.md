Khi chạy ứng dụng JAR có manifest chỉ định điểm vào, thuộc tính nào khai báo lớp khởi chạy?
A. Class-Path trong manifest của JAR.
B. Start-Class trong module descriptor của ứng dụng.
C. Main-Class trong manifest của JAR.
D. Entry-Point trong biến môi trường của tiến trình.
Đáp án đúng: C

Khi khởi chạy bằng java -jar app.jar, dependency bên ngoài được tìm theo cơ chế nào?
A. Theo classpath mặc định của thư mục làm việc hiện tại.
B. Theo thư viện được cài sẵn trong thư mục JDK.
C. Theo Class-Path khai báo trong manifest của JAR.
D. Theo mọi thư mục trong biến PATH của hệ điều hành.
Đáp án đúng: C

Một ứng dụng cần chạy bằng java -cp với nhiều thư viện đặt riêng trong thư mục lib; cách đóng gói nào phù hợp?
A. Một JAR chỉ chứa source để runtime biên dịch.
B. Một WAR bung sẵn để JVM tự nạp dependency.
C. Các thư viện đặt trong bin để launcher tự quét.
D. JAR ứng dụng, thư mục lib và lệnh classpath rõ ràng.
Đáp án đúng: D

Khi chạy ứng dụng với java -jar, lựa chọn nào mô tả đúng classpath truyền bằng -cp?
A. Tùy chọn -cp bị bỏ qua khi dùng chế độ -jar.
B. Classpath từ -cp luôn được nối trước manifest.
C. Classpath từ -cp chỉ áp dụng cho module hệ thống.
D. Classpath từ -cp chỉ được đọc khi thiếu Main-Class.
Đáp án đúng: A

Một ứng dụng web đóng gói thành WAR cần môi trường thực thi nào?
A. Trình quản lý gói hệ điều hành để giải nén WAR.
B. JDK compiler để biên dịch lại từng request.
C. JVM đơn lẻ có Main-Class trong manifest của WAR.
D. Servlet container tương thích với API ứng dụng.
Đáp án đúng: D

Khi triển khai WAR lên servlet container, thư mục WEB-INF/lib thường chứa gì?
A. Thư viện phụ thuộc riêng của web application.
B. Script khởi động và health check của máy chủ.
C. Cấu hình JVM dùng chung cho toàn bộ máy chủ.
D. Module hệ thống của JDK mà container tự biên dịch.
Đáp án đúng: A

Một JAR chứa cả mã ứng dụng và toàn bộ dependency được gọi phổ biến là gì?
A. Thin JAR chỉ tham chiếu thư viện ngoài.
B. Fat JAR chứa ứng dụng và dependency.
C. WAR chuẩn triển khai vào servlet container.
D. JMOD archive chứa module của JDK.
Đáp án đúng: B

Một bản phân phối thin JAR thường cần đi kèm thành phần nào?
A. Servlet container nhúng trong mọi trường hợp.
B. Thư viện phụ thuộc được phân phối riêng.
C. Heap dump để khởi tạo runtime của ứng dụng.
D. Bản sao đầy đủ source code để JVM biên dịch.
Đáp án đúng: B

Khi ứng dụng dùng JPMS, module path khác classpath ở đặc điểm nào?
A. Hỗ trợ module có danh tính và ranh giới đọc.
B. Hai đường dẫn luôn được JVM xử lý giống nhau.
C. Chỉ chứa JAR không có module descriptor.
D. Classpath tự động áp dụng mọi quy tắc JPMS.
Đáp án đúng: A

Muốn tạo runtime Java tối giản bằng jlink, cần cung cấp thông tin nào?
A. Danh sách mọi class trong toàn bộ dependency JAR.
B. Một WAR đã bung cùng servlet container đang chạy.
C. Biến môi trường và tham số JVM của production.
D. Module gốc và dependency module cần cho ứng dụng.
Đáp án đúng: D

jpackage thường được dùng để đạt mục tiêu nào?
A. Tạo application image hoặc gói cài đặt nền tảng.
B. Tạo manifest triển khai container orchestration.
C. Tạo JAR có manifest và tự ký mọi dependency.
D. Tạo module runtime tùy chỉnh chỉ từ source Java.
Đáp án đúng: A

Vì sao runtime image tạo bởi jlink cần được kiểm thử trên môi trường đích?
A. Có thể thiếu module hoặc native component cần thiết.
B. Mọi module đều được tải động từ Maven Central.
C. jlink luôn loại bỏ mọi thư viện chuẩn khỏi runtime.
D. Runtime image chỉ chạy khi có JDK đầy đủ bên cạnh.
Đáp án đúng: A

Trong JVM, -Xmx chủ yếu kiểm soát giới hạn nào?
A. Kích thước stack tối đa cho mỗi thread.
B. Dung lượng tối đa của metaspace.
C. Kích thước heap tối đa của JVM.
D. Số connection tối đa của ứng dụng.
Đáp án đúng: C

Tham số -Dname=value trên dòng lệnh Java dùng để làm gì?
A. Chọn thư mục làm việc trước khi JVM khởi động.
B. Đặt system property cho ứng dụng đọc.
C. Đặt tên module chính trong module path.
D. Đặt biến môi trường cho tiến trình cha.
Đáp án đúng: B

Biến môi trường và Java system property khác nhau ở điểm nào?
A. Hai loại cấu hình tự đồng bộ hai chiều.
B. System property luôn được kế thừa bởi mọi tiến trình con.
C. Một bên thuộc process environment, một bên thuộc JVM.
D. Biến môi trường chỉ tồn tại khi JVM đang chạy.
Đáp án đúng: C

Một container cần thay đổi endpoint database giữa staging và production; cách cấu hình nào phù hợp?
A. Build một JAR riêng chứa endpoint cố định mỗi môi trường.
B. Ghi endpoint vào manifest rồi sửa JAR khi deploy.
C. Đưa endpoint vào tên image để ứng dụng tự phân tích.
D. Nạp cấu hình ngoài artifact theo môi trường chạy.
Đáp án đúng: D

Vì sao không nên đóng secret production trực tiếp vào JAR hoặc image?
A. Secret trong image tự hết hạn khi container dừng.
B. JAR không hỗ trợ dữ liệu nhị phân nên build sẽ lỗi.
C. Secret có thể bị trích xuất từ artifact hoặc layer.
D. JVM không đọc được secret nằm trong file JAR.
Đáp án đúng: C

Một script shell khởi chạy Java ở chế độ foreground nên dùng exec trước lệnh Java để làm gì?
A. Tạo process riêng cho từng tham số JVM.
B. Thay shell bằng JVM để nhận tín hiệu trực tiếp.
C. Giữ shell làm process cha để ghi stdout của JVM.
D. Chạy JVM nền và trả prompt ngay cho người dùng.
Đáp án đúng: B

Trong script khởi chạy, vì sao nên quote biến chứa đường dẫn hoặc tham số có khoảng trắng?
A. Giữ nguyên ranh giới đối số, tránh word splitting.
B. Buộc shell mở rộng wildcard trong mọi giá trị biến.
C. Mã hóa ký tự đặc biệt thành biến môi trường.
D. Ngăn JVM đọc system property từ dòng lệnh.
Đáp án đúng: A

Khi truyền đối số bổ sung vào script khởi chạy, cách nào giữ nguyên từng đối số?
A. Dùng $# để chuyển nội dung của từng đối số.
B. Dùng $@ không quote để giữ nguyên khoảng trắng.
C. Dùng "$@" để chuyển tiếp từng đối số riêng.
D. Dùng "$*" để luôn tạo một đối số cho mọi trường hợp.
Đáp án đúng: C

Khi ứng dụng chạy trong container, exec-form ENTRYPOINT thường có lợi ích nào?
A. Container tự khởi động lại sau mọi lỗi ứng dụng.
B. Shell tự chuyển mọi signal thành Java exception.
C. JVM nhận tín hiệu trực tiếp hơn với vai trò PID 1.
D. Docker tự thêm mọi JVM option từ Dockerfile.
Đáp án đúng: C

Container chạy Java bị dừng khi orchestrator gửi SIGTERM; ứng dụng cần làm gì?
A. Ngừng nhận việc mới và hoàn tất việc đang chạy.
B. Bỏ qua tín hiệu và chờ SIGKILL ngay lập tức.
C. Ghi heap dump rồi tiếp tục nhận request mới.
D. Tắt logging trước và chờ JVM tự phát hiện shutdown.
Đáp án đúng: A

Một health endpoint trả HTTP 200 ngay khi process vừa mở cổng, dù chưa kết nối database; probe nào phát hiện ứng dụng chưa sẵn sàng?
A. Startup probe thay thế mọi kiểm tra dependency mãi mãi.
B. Readiness probe kiểm tra khả năng nhận traffic.
C. Image scan xác nhận database đã sẵn sàng.
D. Liveness probe chỉ xác nhận process còn tồn tại.
Đáp án đúng: B

Liveness probe thất bại liên tục thường dẫn đến hành động nào từ orchestrator?
A. Tăng heap JVM đến khi endpoint trả thành công.
B. Chỉ ngừng gửi traffic nhưng giữ process nguyên trạng.
C. Tự động rollback image về digest của lần trước.
D. Khởi động lại container theo restart policy.
Đáp án đúng: D

Một ứng dụng cần thời gian dài để khởi tạo cache trước khi nhận traffic; probe nào phù hợp để tránh restart quá sớm?
A. Readiness probe vô hiệu hóa mọi kiểm tra khởi động.
B. Liveness probe được cấu hình thất bại ngay từ đầu.
C. Image pull policy trì hoãn probe đến lần deploy sau.
D. Startup probe dành thời gian cho giai đoạn khởi động.
Đáp án đúng: D

Build cùng source và dependency nhưng artifact thay đổi checksum giữa hai lần build; yếu tố nào nên kiểm tra trước?
A. Process Java trên máy build có PID khác nhau.
B. Số lần chạy health check sau khi đóng gói.
C. Timestamp, thứ tự archive và toolchain của build.
D. Tên artifact có chứa số phiên bản khác nhau.
Đáp án đúng: C

Để build có thể tái lập, cách quản lý dependency nào phù hợp?
A. Pin phiên bản và kiểm soát nguồn dependency.
B. Chỉ lưu tên thư viện mà không lưu phiên bản.
C. Dùng phiên bản mới nhất để nhận bản vá tự động.
D. Cho phép build tải dependency bất kỳ từ mirror.
Đáp án đúng: A

SBOM trong quy trình phát hành cung cấp thông tin nào?
A. Heap dump và thread dump của ứng dụng đang chạy.
B. Danh mục component và dependency trong artifact.
C. Danh sách người dùng được cấp quyền production.
D. Bản đồ network route giữa các container.
Đáp án đúng: B

Chữ ký số artifact giúp người triển khai xác minh điều gì?
A. Ứng dụng tương thích với mọi phiên bản JVM.
B. Nguồn phát hành và tính toàn vẹn theo khóa tin cậy.
C. Artifact đã vượt qua mọi bài kiểm thử hiệu năng.
D. Artifact không chứa lỗ hổng bảo mật đã biết.
Đáp án đúng: B

Trong multi-stage container build, mục tiêu chính của build stage là gì?
A. Thực hiện health check trước khi tạo container image.
B. Chạy ứng dụng production và giữ compiler trong image cuối.
C. Biên dịch và tạo artifact trước runtime stage.
D. Lưu secret build để runtime đọc trực tiếp từ layer.
Đáp án đúng: C

Vì sao runtime container image nên chứa ít công cụ và dependency không cần thiết?
A. Tăng số layer để cache build chính xác hơn.
B. Giảm kích thước image và bề mặt tấn công.
C. Bảo đảm ứng dụng không cần cấu hình runtime nữa.
D. Giúp JVM tự biên dịch dependency khi khởi động.
Đáp án đúng: B

Chạy container Java bằng user không phải root mang lại lợi ích nào?
A. Tự động mã hóa biến môi trường khi process khởi động.
B. Giảm quyền của tiến trình nếu ứng dụng bị khai thác.
C. Ngăn container truy cập network namespace của chính nó.
D. Bảo đảm mọi file trong image đều chỉ đọc.
Đáp án đúng: B

Một ứng dụng cần ghi file tạm khi root filesystem của container ở chế độ read-only; giải pháp nào phù hợp?
A. Ghi dữ liệu tạm vào layer bất biến của image.
B. Chuyển user chạy container thành root.
C. Tắt filesystem permission trong image manifest.
D. Mount writable volume riêng cho vùng cần ghi.
Đáp án đúng: D

Khi triển khai image mới, vì sao nên tham chiếu bằng digest thay vì chỉ dùng tag mutable?
A. Tag mutable luôn bị registry từ chối khi image thay đổi.
B. Digest tự cập nhật để trỏ đến bản vá mới nhất.
C. Tag không thể được dùng trong manifest triển khai.
D. Digest định danh nội dung image bất biến.
Đáp án đúng: D

Một bản phát hành cần quay lui sau khi phiên bản mới gây lỗi; thông tin nào giúp tái triển khai đúng artifact cũ?
A. Artifact hoặc image digest đã lưu cùng metadata.
B. Tag latest trên registry tại thời điểm rollback.
C. Mã thoát của script deploy lần gần nhất.
D. Tên nhánh source hiện tại trên máy developer.
Đáp án đúng: A

Ứng dụng cần nâng cấp schema dữ liệu đồng thời với rolling deployment; chiến lược nào giảm rủi ro tương thích?
A. Migration tương thích ngược qua các giai đoạn.
B. Rollback binary và giả định dữ liệu tự quay về cũ.
C. Xóa schema cũ ngay trước khi khởi động instance mới.
D. Deploy code mới lên mọi node trước khi kiểm tra schema.
Đáp án đúng: A

Một service khởi chạy thành công nhưng thoát ngay sau đó; thông tin nào nên kiểm tra đầu tiên?
A. Số layer image và thứ tự layer trong registry.
B. Mức sử dụng CPU node trước khi deploy.
C. Số replica của backend lưu trữ artifact.
D. Exit code, stderr và log khởi động của process.
Đáp án đúng: D
