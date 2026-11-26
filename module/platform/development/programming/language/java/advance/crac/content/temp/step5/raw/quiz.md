Câu 1. Mục tiêu chính của Java CRaC là gì khi một ứng dụng đã khởi tạo đầy đủ?
A. Lưu classpath vào archive để JVM tự biên dịch lại mỗi khi chạy.
B. Lưu thread dump làm dữ liệu khởi động JVM ở lần chạy sau.
C. Lưu response cache vào JAR để tránh mọi truy vấn database.
D. Lưu trạng thái JVM vào image để khôi phục gần điểm checkpoint.
Đáp án đúng: D

Câu 2. Khác biệt quan trọng giữa checkpoint JVM CRaC và Class Data Sharing là gì?
A. CDS giữ heap cùng trạng thái thread tại thời điểm ứng dụng chạy.
B. CDS khôi phục socket và kết nối database đã đăng nhập trước đó.
C. CRaC chỉ lưu metadata class và bỏ qua trạng thái đối tượng.
D. Checkpoint có thể giữ heap và trạng thái runtime đã khởi tạo.
Đáp án đúng: D

Câu 3. Vì sao checkpoint sau giai đoạn warm-up có thể giảm độ trễ ban đầu khi restore?
A. Restore biến bytecode Java thành native executable không cần JVM.
B. JVM phục hồi trạng thái đã chạy, gồm cả tối ưu hóa JIT trước đó.
C. Checkpoint xóa mọi đối tượng heap để giảm thời gian GC sau restore.
D. Restore buộc trình biên dịch JIT chạy lại từ đầu mọi phương thức.
Đáp án đúng: B

Câu 4. Điều kiện nền tảng nào cần có để thực hiện checkpoint/restore thực sự bằng CRaC?
A. Dùng Java serialization để thay image của cả tiến trình JVM.
B. Thêm thư viện API CRaC vào JDK tiêu chuẩn rồi chạy checkpoint.
C. Dùng JDK hỗ trợ CRaC và checkpoint engine tương thích với host.
D. Bật CDS cùng heap dump để khôi phục thread đang thực thi.
Đáp án đúng: C

Câu 5. Khi khởi chạy JVM hỗ trợ CRaC, option nào định nghĩa thư mục lưu checkpoint image?
A. Dùng `-XX:StartFlightRecording=PATH` khi khởi động JVM.
B. Dùng `-XX:SharedArchiveFile=PATH` khi khởi động JVM.
C. Dùng `-XX:CRaCCheckpointTo=PATH` khi khởi động JVM.
D. Dùng `-XX:CRaCRestoreFrom=PATH` khi khởi động JVM.
Đáp án đúng: C

Câu 6. Muốn khởi tạo JVM từ checkpoint image đã tạo, option nào là phù hợp?
A. Dùng `-XX:CRaCRestoreFrom=PATH` trên runtime CRaC.
B. Dùng `-XX:CRaCCheckpointTo=PATH` trên runtime CRaC.
C. Dùng `-XX:SharedArchiveFile=PATH` trên runtime CRaC.
D. Dùng `-XX:HeapDumpPath=PATH` trên runtime CRaC.
Đáp án đúng: A

Câu 7. Khi một JVM CRaC đang chạy, lệnh điều khiển nào có thể yêu cầu checkpoint?
A. Dùng `jcmd <pid> JDK.checkpoint` trên JVM hỗ trợ CRaC.
B. Dùng `jcmd <pid> Thread.print` để chụp đủ trạng thái JVM.
C. Dùng `jcmd <pid> VM.flags` để tự động tạo image restore.
D. Dùng `jcmd <pid> GC.heap_dump` để khôi phục tiến trình.
Đáp án đúng: A

Câu 8. Trong API CRaC, lời gọi nào có thể yêu cầu checkpoint từ mã Java?
A. Gọi `Runtime.getRuntime().gc()` để tạo ảnh trạng thái.
B. Gọi `System.exit(0)` để chuyển sang tiến trình restore.
C. Gọi `Core.checkpointRestore()` trên runtime hỗ trợ CRaC.
D. Gọi `Thread.currentThread().interrupt()` để lưu toàn JVM.
Đáp án đúng: C

Câu 9. Lớp Java cần nhận thông báo trước checkpoint và sau restore thì triển khai interface nào?
A. Triển khai `java.io.Serializable` với hai lifecycle callbacks.
B. Triển khai `org.crac.Resource` với hai lifecycle callbacks.
C. Triển khai `java.util.concurrent.Callable` để JVM tạo checkpoint.
D. Triển khai `java.lang.AutoCloseable` để JVM tự mở lại resource.
Đáp án đúng: B

Câu 10. Một đối tượng implement `org.crac.Resource` muốn nhận callback phải làm gì?
A. Đăng ký với `ShutdownHook` để thay thế toàn bộ context.
B. Chỉ khai báo `implements Resource` là đủ để tự được quét.
C. Đăng ký instance qua `Core.getGlobalContext().register(...)`.
D. Chỉ gắn annotation `@PostConstruct` trên lớp resource.
Đáp án đúng: C

Câu 11. Mục đích phù hợp của `beforeCheckpoint(...)` trong CRaC là gì?
A. Ngừng việc mới và đóng socket/file trước khi checkpoint.
B. Chạy lại constructor của singleton đã khởi tạo.
C. Khôi phục TCP connection theo địa chỉ sau restore.
D. Tái cấp token khi restore trên môi trường mới.
Đáp án đúng: A

Câu 12. Mục đích phù hợp của `afterRestore(...)` trong CRaC là gì?
A. Chuyển mọi thread JVM đang chạy thành daemon thread.
B. Ghi toàn bộ heap hiện tại xuống file checkpoint mới.
C. Xóa callback `beforeCheckpoint` khỏi Java classpath.
D. Mở lại kết nối và đồng bộ tài nguyên với môi trường mới.
Đáp án đúng: D

Câu 13. Service giữ TCP socket đang kết nối đến backend tại checkpoint; hướng xử lý hợp lý là gì?
A. Giữ socket nguyên vẹn để backend tiếp tục phiên TCP cũ.
B. Đổi socket sang non-blocking để tự vượt qua checkpoint.
C. Đóng socket trước checkpoint rồi kết nối lại sau restore.
D. Tăng TCP keepalive để kết nối không cần lifecycle callback.
Đáp án đúng: C

Câu 14. Với JDBC connection pool đã kết nối trước checkpoint, nên phối hợp tài nguyên thế nào?
A. Tăng maximumPoolSize để pool sống qua restore mà không đổi.
B. Đóng pool trước checkpoint, tạo kết nối mới sau restore.
C. Lưu các JDBC connection sống vào image để dùng ở node khác.
D. Chỉ refresh DNS cache rồi tiếp tục các session JDBC cũ.
Đáp án đúng: B

Câu 15. Trước khi checkpoint có dữ liệu ghi file còn trong buffer, thao tác nào hợp lý?
A. Flush dữ liệu cần bảo toàn rồi đóng file handle liên quan.
B. Giữ file handle mở để flush tự thực hiện trên node restore.
C. Đổi tên file trên ổ đĩa mà không đẩy phần buffer chưa ghi.
D. Chỉ cập nhật timestamp của file trước khi chụp image.
Đáp án đúng: A

Câu 16. Một thư viện giữ file descriptor không được giải phóng, biểu hiện checkpoint nào có thể xảy ra?
A. CRaC mặc định bỏ qua mọi handle và xem snapshot hợp lệ.
B. Checkpoint thất bại vì runtime còn open file descriptor.
C. Restore tự cấp lại descriptor gốc mà không cần xử lý.
D. Checkpoint tự chuyển mọi descriptor thành file JSON metadata.
Đáp án đúng: B

Câu 17. Vì sao một job chạy nền bằng thread pool cần thiết kế lifecycle cho CRaC?
A. Chờ đến sau restore mới shutdown executor còn tác vụ dở.
B. Cần tạm dừng công việc và tái khởi động executor phù hợp.
C. Giữ nguyên task queue dù phụ thuộc vào kết nối đã bị đóng.
D. Chuyển executor sang daemon threads để tránh việc dọn dẹp.
Đáp án đúng: B

Câu 18. Khi restore ở máy có hostname hoặc endpoint dịch vụ khác, bước nào phù hợp?
A. Đọc lại cấu hình môi trường rồi kết nối lại dịch vụ.
B. Dùng nguyên mọi địa chỉ IP đã cache trước checkpoint.
C. Ghi đè biến môi trường từ heap cũ lên cấu hình host mới.
D. Chỉ đổi tên tệp image để JVM tự nhận diện hostname.
Đáp án đúng: A

Câu 19. Token truy cập có thời hạn đã được nạp trước checkpoint; cần làm gì khi restore muộn?
A. Chỉ kéo dài timeout HTTP, token cũ sẽ tự được server chấp nhận.
B. Kiểm tra hạn token và lấy lại credential nếu đã hết hiệu lực.
C. Đổi giá trị issuer trong heap để token cũ thành token mới.
D. Tin token còn hợp lệ vì đồng hồ JVM được quay về lúc checkpoint.
Đáp án đúng: B

Câu 20. Ứng dụng dùng TLS client kết nối server trước checkpoint; cần lưu ý điều gì sau restore?
A. Dùng tiếp phiên TLS cũ vì secret đã được ghi trong heap image.
B. Tắt xác minh hostname khi gặp lỗi reconnect sau restore.
C. Thiết lập TLS connection mới và kiểm tra server certificate.
D. Chỉ đổi tên socket để TLS session từ máy khác còn hợp lệ.
Đáp án đúng: C

Câu 21. Vì sao checkpoint image CRaC là dữ liệu nhạy cảm cần được bảo vệ?
A. Image chỉ chứa bytecode nên không thể mang thông tin phiên.
B. Image chỉ chứa log đã ẩn dữ liệu nhạy cảm của ứng dụng.
C. Image có thể chứa mật khẩu, access token và dữ liệu heap.
D. Image được mã hóa mặc định bằng private key của JVM.
Đáp án đúng: C

Câu 22. Nếu phải phân phối checkpoint image giữa môi trường triển khai, biện pháp nào quan trọng?
A. Đưa mật khẩu gốc vào image để đơn giản hóa phần khôi phục.
B. Giới hạn truy cập và bảo vệ image cả khi lưu và khi chuyển.
C. Chỉ đổi tên file image thành `.bin` rồi coi như an toàn.
D. Công khai image để các node tự tối ưu theo CPU architecture.
Đáp án đúng: B

Câu 23. Với snapshot JVM tạo ở một máy và restore sang máy khác, yếu tố nào cần kiểm tra?
A. Tính tương thích JDK, hệ điều hành và kiến trúc CPU.
B. Chỉ cần JDK cùng phiên bản Java, khác kiến trúc vẫn phù hợp.
C. Dung lượng heap bằng nhau sẽ bảo đảm checkpoint tương thích.
D. Thư mục image cùng tên giúp restore qua các OS khác nhau.
Đáp án đúng: A

Câu 24. Trên Linux, CRaC thường dựa vào cơ chế nền nào để snapshot tiến trình?
A. CRIU có thể checkpoint và restore tiến trình ở mức OS.
B. CDS snapshot socket, file handles và page table của JVM.
C. JFR lưu trạng thái JVM để khôi phục cả tiến trình Java.
D. JVMTI chuyển toàn bộ tiến trình thành serialized stream.
Đáp án đúng: A

Câu 25. Khi checkpoint thất bại vì socket còn mở, bước chẩn đoán hợp lý nào?
A. Bỏ qua lỗi vì restore sẽ tự sửa socket trên máy đích.
B. Xóa bảng DNS cache rồi coi mọi descriptor đã đóng.
C. Xem lỗi checkpoint để xác định descriptor chưa đóng.
D. Chỉ tăng heap maximum rồi thử lại không cần thay code.
Đáp án đúng: C

Câu 26. Ứng dụng có tác vụ theo lịch fixed-rate; quãng nghỉ dài từ checkpoint đến restore gây rủi ro gì?
A. Scheduler tự đổi sang fixed-delay sau lần restore đầu.
B. Thời điểm checkpoint được tính lại cho mọi tác vụ.
C. Lịch chạy không còn phụ thuộc thời gian khi đã restore.
D. Có thể dồn những lần chạy bị lỡ, cần xem lại lịch.
Đáp án đúng: D

Câu 27. Ứng dụng ghi sự kiện ra broker trước checkpoint; sau restore cần phòng ngừa điều gì?
A. Giữ nguyên broker connection để dùng ACK của phiên cũ.
B. Ngăn phát lại ngoài ý muốn bằng idempotency và trạng thái gửi.
C. Reset mọi offset broker để tránh sự kiện bị gửi trùng.
D. Tắt retry vì checkpoint bảo đảm đúng một lần giao event.
Đáp án đúng: B

Câu 28. Tại sao không nên đo mỗi thời gian chạy `java` khi so sánh CRaC với cold start?
A. Dung lượng image đại diện trực tiếp cho readiness của service.
B. Thời gian chạy lệnh đã bao gồm mọi độ trễ DB khi khởi động.
C. Giá trị startup đơn lẻ phản ánh được latency sau warm-up.
D. Cần đo đến khi API sẵn sàng và phản hồi request thật.
Đáp án đúng: D

Câu 29. Muốn so sánh độ trễ request sau cold start và sau restore, phương pháp nào phù hợp?
A. So sánh request đầu tiên của hai môi trường có tải khác nhau.
B. Đếm số class loaded để suy ra latency của mọi request.
C. Dùng kích thước JAR làm chỉ số đại diện cho p95 API.
D. Chạy workload giống nhau và đo các phân vị latency nhiều lần.
Đáp án đúng: D

Câu 30. Khi đánh giá chi phí vận hành của CRaC, bộ chỉ số bộ nhớ nào hữu ích?
A. Đo RSS sau restore và kích thước checkpoint image trên đĩa.
B. Đo heap committed và bỏ qua phần bộ nhớ ngoài heap.
C. Đếm thread Java như một đại diện cho native memory.
D. Thay RSS bằng Xmx vì hai số đều biểu thị RAM thực.
Đáp án đúng: A

Câu 31. Một service kiểm tra CRaC bằng integration test; kịch bản nào cho bằng chứng mạnh nhất?
A. Khởi tạo service bean rồi coi startup thành công là đủ.
B. Bật CDS để thay thế toàn bộ quy trình checkpoint thật.
C. Unit test `Resource` bằng mock nhưng không chạy restore.
D. Checkpoint, restore, thử API và xác minh DB/reconnect hoạt động.
Đáp án đúng: D

Câu 32. Trong ứng dụng Spring hỗ trợ CRaC, hai hook `Lifecycle.stop/start` hữu ích thế nào?
A. Stop khởi tạo DB lần đầu; start xóa các bảng đã tạo trước đó.
B. Stop tạo snapshot class metadata; start biên dịch lại bytecode.
C. Stop ghi thread dump; start nạp heap dump để tiếp tục JVM.
D. Stop đóng tài nguyên trước checkpoint; start mở lại sau restore.
Đáp án đúng: D
