Câu 1: Java 26 bổ sung hỗ trợ HTTP/3 trực tiếp cho API nào?
A. `java.net.http.HttpClient` của JDK.
B. `java.net.HttpURLConnection` của JDK.
C. `java.nio.channels.SocketChannel` của JDK.
D. `com.sun.net.httpserver.HttpServer` của JDK.
Đáp án đúng: A

Câu 2: Trong `HttpClient.Builder`, cấu hình nào thể hiện ưu tiên dùng HTTP/3?
A. `version(HttpClient.Version.HTTP_1_1)`.
B. `version(HttpClient.Version.HTTP_2)`.
C. `version(HttpClient.Version.HTTP_3)`.
D. `followRedirects(HttpClient.Redirect.NORMAL)`.
Đáp án đúng: C

Câu 3: HTTP/3 dùng cơ chế truyền tải nào dưới tầng HTTP?
A. TLS độc lập vận hành trên TCP.
B. QUIC vận hành trên nền UDP.
C. WebSocket vận hành trên nền TCP.
D. HTTP/2 vận hành trên nền TCP.
Đáp án đúng: B

Câu 4: Để biết phiên bản HTTP thực tế của phản hồi, nên kiểm tra gì?
A. `HttpRequest.version()` của yêu cầu.
B. `HttpResponse.version()` của phản hồi.
C. `HttpClient.version()` của client.
D. `HttpClient.proxy()` của client.
Đáp án đúng: B

Câu 5: HTTP/3 cải thiện điểm nào liên quan tới nhiều luồng yêu cầu đồng thời?
A. TCP của HTTP/3 bảo đảm không có bất kỳ mất gói.
B. HTTP/3 vô hiệu hóa cơ chế kiểm soát tắc nghẽn.
C. HTTP/3 gửi mỗi yêu cầu qua một kết nối TCP mới.
D. QUIC giảm việc một luồng mất gói chặn luồng khác.
Đáp án đúng: D

Câu 6: Trong JDK 26, hỗ trợ HTTP/3 của HttpClient thuộc loại nào?
A. Tùy chọn thử nghiệm, phải bật cờ JVM nội bộ.
B. API preview, phải bật `--enable-preview`.
C. Module incubator, phải bật `--add-modules`.
D. Tính năng chính thức, không cần bật preview.
Đáp án đúng: D

Câu 7: Khi chuyển ứng dụng `java.net.http` sang HTTP/3, điều nào đúng?
A. Có thể dùng lại luồng tạo `HttpRequest` và nhận `HttpResponse`.
B. Phải gọi trực tiếp QUIC socket thay cho `HttpClient.send`.
C. Phải thay toàn bộ `HttpRequest` bằng request từ Servlet API.
D. Phải chuyển toàn bộ HTTP client sang `HttpURLConnection`.
Đáp án đúng: A

Câu 8: Giao thức nào bảo vệ phiên HTTP/3 trong QUIC?
A. TLS 1.3 được tích hợp cùng QUIC.
B. TLS 1.3 dùng trên một kết nối TCP riêng.
C. DTLS 1.2 hoạt động thay cho QUIC.
D. TLS 1.2 được đóng gói ở tầng HTTP.
Đáp án đúng: A

Câu 9: Trạng thái của primitive type patterns trong JDK 26 là gì?
A. JEP 529, lần incubator thứ mười một.
B. JEP 530, một API đã chính thức.
C. JEP 525, lần preview thứ sáu.
D. JEP 530, lần preview thứ tư.
Đáp án đúng: D

Câu 10: Cặp lệnh nào phù hợp để biên dịch và chạy mã dùng preview Java 26?
A. `javac --enable-preview --release 26`; `java` không bật preview.
B. `javac --enable-preview --release 26`; `java --enable-preview`.
C. `javac --release 26`; `java --enable-preview`.
D. `javac --enable-preview --release 25`; `java --enable-preview`.
Đáp án đúng: B

Câu 11: Trong preview Java 26, các kiểu nguyên thủy nào được mở rộng làm selector `switch`?
A. `long`, `float`, `double` và `boolean`.
B. `long`, `float`, `double` và `char`.
C. `long`, `float`, `short` và `boolean`.
D. `byte`, `short`, `char` và `int`.
Đáp án đúng: A

Câu 12: Với preview Java 26, `int x = 128; x instanceof byte b` cho kết quả nào?
A. Lỗi runtime vì chuyển kiểu gây mất dữ liệu.
B. `false`, vì 128 nằm ngoài miền `byte`.
C. `true`, vì `instanceof` chỉ so sánh kiểu tĩnh.
D. `true`, vì Java luôn ép `int` về `byte`.
Đáp án đúng: B

Câu 13: Với preview Java 26, `double x = 3.5; x instanceof int n` có kết quả nào?
A. `true`, vì cả hai đều là kiểu số nguyên thủy.
B. `false`, do phép chuyển sang `int` không chính xác.
C. Lỗi runtime vì `double` không thể chuyển sang `int`.
D. `true`, vì số thực được làm tròn trước khi so.
Đáp án đúng: B

Câu 14: Với preview Java 26, `int x = 100; x instanceof byte b` có kết quả nào?
A. `true`, vì giá trị 100 biểu diễn chính xác bằng `byte`.
B. `false`, vì `instanceof` chỉ chấp nhận kiểu tham chiếu.
C. Lỗi biên dịch vì không thể kết hợp `int` và `byte`.
D. `false`, vì chuyển `int` xuống `byte` luôn bị từ chối.
Đáp án đúng: A

Câu 15: Mệnh đề `when` trong một `case` có pattern được dùng để làm gì?
A. Ép JVM tự chuyển mọi pattern sang kiểu `Object`.
B. Bỏ qua kiểm tra tính đầy đủ của mọi nhánh `switch`.
C. Cho phép mọi nhánh `case` tiếp tục chạy xuyên qua.
D. Bổ sung điều kiện boolean giới hạn pattern khớp.
Đáp án đúng: D

Câu 16: Kiểm tra dominance chặt hơn ở JEP 530 nhằm phát hiện gì?
A. Một biểu thức `case` bị JVM biên dịch JIT nhiều lần.
B. Một nhánh `case` bị nhánh trước bao phủ và không thể tới.
C. Một nhánh `case` có thời gian chạy chậm hơn nhánh khác.
D. Một biến `case` làm thay đổi thứ tự khai báo trường lớp.
Đáp án đúng: B

Câu 17: Khi chuyển mã dùng primitive pattern preview từ JDK 26 lên JDK mới, nên làm gì?
A. Giữ bytecode JDK 26 vì preview luôn tương thích nhị phân.
B. Chỉ đổi `JAVA_HOME` vì cú pháp preview không bao giờ đổi.
C. Bỏ toàn bộ bài kiểm thử vì preview đã được chuẩn hóa.
D. Kiểm tra lại JEP, biên dịch và chạy thử trên JDK đích.
Đáp án đúng: D

Câu 18: Trong JDK 26, Structured Concurrency có trạng thái nào?
A. JEP 530, preview lần thứ tư.
B. JEP 525, API chính thức ổn định.
C. JEP 529, incubator lần thứ mười một.
D. JEP 525, preview lần thứ sáu.
Đáp án đúng: D

Câu 19: Trong API Structured Concurrency của JDK 26, cách mở scope hợp lệ là gì?
A. Gọi `Executors.newFixedThreadPool(4)` trong `try-with-resources`.
B. Gọi `Executors.newSingleThreadExecutor()` trong `try-with-resources`.
C. Gọi `StructuredTaskScope.open()` trong `try-with-resources`.
D. Gọi `Executors.newVirtualThreadPerTaskExecutor()` trong `try-with-resources`.
Đáp án đúng: C

Câu 20: Mặc định `StructuredTaskScope.fork(...)` tạo kiểu thread nào?
A. Virtual thread để chạy tác vụ con.
B. Daemon platform thread dùng chung toàn JVM.
C. Platform thread trong một nhóm cố định.
D. ForkJoin worker thread do common pool cấp.
Đáp án đúng: A

Câu 21: Với `StructuredTaskScope.open()` mặc định, `join()` xử lý lỗi subtask thế nào?
A. Trả danh sách mọi kết quả kể cả khi có subtask thất bại.
B. Trả kết quả của subtask hoàn thành nhanh nhất bất kể lỗi.
C. Trả `null` khi tất cả thành công; ném lỗi khi có subtask thất bại.
D. Bỏ qua mọi lỗi của subtask và luôn trả về `null`.
Đáp án đúng: C

Câu 22: Khi đóng StructuredTaskScope mà còn subtask chưa kết thúc, điều nào đúng?
A. Scope bỏ qua mọi tác vụ mà không chờ hoặc hủy.
B. Scope giữ tác vụ chạy nền và trả về ngay cho caller.
C. Scope tự chuyển mọi tác vụ còn lại sang common pool.
D. Scope hủy tác vụ còn lại và chờ các thread kết thúc.
Đáp án đúng: D

Câu 23: Với `Joiner.anySuccessfulResultOrThrow()`, `join()` trả gì nếu có tác vụ thành công?
A. Danh sách kết quả của mọi subtask thành công.
B. Kết quả của subtask thành công đầu tiên.
C. Kết quả của subtask bắt đầu đầu tiên.
D. Giá trị `null` kể cả khi subtask thành công.
Đáp án đúng: B

Câu 24: Với `Joiner.allSuccessfulOrThrow()`, `join()` trả gì khi mọi subtask thành công?
A. Một stream các đối tượng subtask đã hoàn tất.
B. Kết quả từ subtask kết thúc cuối cùng.
C. Một map các tên thread đến kết quả tính toán.
D. Giá trị `null` thay cho toàn bộ các subtask.
Đáp án đúng: A

Câu 25: Công cụ nào giúp xem cây phạm vi và subtask của Structured Concurrency?
A. Heap histogram lấy bằng công cụ `jcmd`.
B. Thread dump lấy bằng công cụ `jcmd`.
C. Báo cáo tối ưu JIT lấy bằng `-XX:+PrintCompilation`.
D. Danh sách module lấy bằng lệnh `java --list-modules`.
Đáp án đúng: B

Câu 26: Vector API có trạng thái nào trong JDK 26?
A. JEP 525, lần preview thứ sáu.
B. JEP 517, tính năng chuẩn HTTP/3.
C. JEP 529, lần incubator thứ mười một.
D. JEP 529, lần preview thứ mười một.
Đáp án đúng: C

Câu 27: Module chứa Vector API của JDK 26 tên là gì?
A. `jdk.incubator.vector` trong JDK.
B. `java.util.concurrent` trong JDK.
C. `java.net.http` trong JDK.
D. `jdk.crypto.ec` trong JDK.
Đáp án đúng: A

Câu 28: Để ứng dụng dùng module Vector API incubator, cần cơ chế kích hoạt nào?
A. Chỉ bật `--enable-preview` không cần thêm module.
B. Dùng `--add-opens java.base/java.lang=ALL-UNNAMED`.
C. Thêm module qua `--add-modules jdk.incubator.vector`.
D. Chỉ cấu hình `--enable-native-access=ALL-UNNAMED`.
Đáp án đúng: C

Câu 29: Trong Vector API, `VectorSpecies` diễn tả điều gì?
A. Số thread tối đa dành cho một phép toán vector.
B. Định dạng mạng dùng để truyền dữ liệu vector.
C. Cơ chế thu gom rác cho bộ đệm vector.
D. Kiểu phần tử và hình dạng số lane của vector.
Đáp án đúng: D

Câu 30: Khi độ dài mảng không chia hết số lane, `VectorMask` giúp gì?
A. Tăng kích thước mảng thành bội số của lane.
B. Tự phân phối vector cho mọi lõi CPU hiện có.
C. Chỉ kích hoạt các lane còn phần tử hợp lệ.
D. Giữ một bản sao đầy đủ của mảng đầu vào.
Đáp án đúng: C

Câu 31: Để quyết định dùng Vector API thay vòng lặp scalar, cần kiểm chứng điều gì?
A. Mặc định mọi phép tính scalar đều bị loại bỏ.
B. Chỉ nhìn số lane mà không đo tác động bộ nhớ.
C. Benchmark trên CPU mục tiêu và dữ liệu thực tế.
D. Giả định mọi CPU đều chạy vector nhanh như nhau.
Đáp án đúng: C

Câu 32: Trạng thái PEM Encodings of Cryptographic Objects trong JDK 26 là gì?
A. JEP 524, bản preview thứ hai.
B. JEP 500, chế độ cảnh báo reflection.
C. JEP 529, module incubator thứ mười một.
D. JEP 524, phiên bản API chính thức.
Đáp án đúng: A

Câu 33: API nào được JDK 26 cung cấp để mã hóa đối tượng mật mã sang PEM?
A. `java.security.KeyFactory` thuộc API chính thức.
B. `java.security.MessageDigest` thuộc API chính thức.
C. `java.security.cert.CertificateFactory` thuộc API chính thức.
D. `java.security.PEMEncoder` thuộc API preview.
Đáp án đúng: D

Câu 34: Trong JDK 26 preview, API nào giải mã dữ liệu PEM thành đối tượng hỗ trợ?
A. `java.security.Signature` thuộc API chính thức.
B. `java.security.KeyStore` thuộc API chính thức.
C. `java.security.SecureRandom` thuộc API chính thức.
D. `java.security.PEMDecoder` thuộc API preview.
Đáp án đúng: D

Câu 35: Định dạng PEM thông thường gồm những thành phần nào?
A. Dữ liệu Base64 giữa header và footer nhận diện loại.
B. Chuỗi hex kèm checksum SHA-256 ở cuối mỗi dòng.
C. Chuỗi JSON có field `signature` và `algorithm`.
D. Byte DER thuần lưu trực tiếp không có giới hạn văn bản.
Đáp án đúng: A

Câu 36: Sau khi giải mã chứng chỉ từ PEM, bước nào vẫn cần thiết khi dùng để tin cậy kết nối?
A. Tin tưởng mặc định vì chứng chỉ đã có định dạng PEM.
B. Bỏ kiểm tra ngày hết hạn do PEM bảo đảm tính hợp lệ.
C. Kiểm tra chuỗi tin cậy và chính sách xác thực chứng chỉ.
D. Tin tưởng vì dữ liệu mã hóa Base64 không bị sửa.
Đáp án đúng: C

Câu 37: Trong JDK 26, `LazyConstant` được phân loại thế nào?
A. JEP 500, chế độ cảnh báo final field.
B. JEP 526, API chuẩn đã ổn định.
C. JEP 529, module incubator thứ mười một.
D. JEP 526, API preview lần thứ hai.
Đáp án đúng: D

Câu 38: Với `LazyConstant.of(supplier)`, thời điểm nào supplier được dùng để khởi tạo giá trị?
A. Khi trình biên dịch nạp bytecode vào JVM.
B. Lần đầu gọi `get()` trên lazy constant.
C. Ngay lúc gọi phương thức tĩnh `of()`.
D. Mỗi lần gọi `get()` trên lazy constant.
Đáp án đúng: B

Câu 39: Sau khi `LazyConstant.get()` khởi tạo thành công, các lần gọi tiếp theo thế nào?
A. Tự đặt nội dung về `null` sau mỗi lần đọc.
B. Tính lại supplier mỗi lần đọc nội dung.
C. Tạo đối tượng mới rồi thay nội dung cũ.
D. Nhận lại nội dung đã thiết lập trước đó.
Đáp án đúng: D

Câu 40: Nếu nhiều thread đồng thời gọi `get()` trên một `LazyConstant`, bảo đảm nào đúng?
A. Các thread buộc chạy supplier theo thứ tự đến.
B. Mọi thread đều phải chạy computing function riêng.
C. Chỉ một thread được chọn chạy computing function.
D. Các thread luôn nhận các giá trị được tính khác nhau.
Đáp án đúng: C

Câu 41: Trong API preview JDK 26, `List.ofLazy(size, function)` khởi tạo phần tử ra sao?
A. Từng vị trí chỉ được tính khi ghi bằng `set()`.
B. Toàn bộ phần tử được tính ngay lúc tạo list.
C. Mỗi vị trí được tính khi truy cập lần đầu.
D. Mỗi lần truy cập đều gọi lại function cho vị trí.
Đáp án đúng: C

Câu 42: JEP 516 cải tiến AOT object caching hỗ trợ bộ gom rác nào?
A. Chỉ Parallel GC vì cache cần stop-the-world.
B. Mọi GC tương thích, bao gồm cả ZGC.
C. Chỉ Serial GC vì cache có cấu trúc tuyến tính.
D. Chỉ G1 GC vì cache phụ thuộc region.
Đáp án đúng: B

Câu 43: Khác biệt chính của AOT object caching trong JDK 26 là gì?
A. Đọc tuần tự dữ liệu cache độc lập với kiểu GC.
B. Memory-map trực tiếp cache có layout riêng của G1.
C. Tắt class loading để chỉ dùng snapshot heap.
D. Chuyển mọi đối tượng AOT sang bytecode của ZGC.
Đáp án đúng: A

Câu 44: Khi đánh giá lợi ích AOT cache, nhóm chỉ số nào sát mục tiêu nhất?
A. Tổng thread được tạo nhưng không đo thời gian chạy.
B. Dung lượng mã nguồn và số file Java được biên dịch.
C. Thời gian startup và warmup trên workload thực.
D. Số HTTP request thành công nhưng không đo thời gian.
Đáp án đúng: C

Câu 45: JEP 522 cải thiện G1 GC bằng hướng nào?
A. Thay hoàn toàn G1 bằng bộ thu gom ZGC.
B. Chuyển mọi thread ứng dụng thành GC worker.
C. Giảm đồng bộ giữa thread ứng dụng và GC.
D. Dừng việc xử lý vùng nhớ thế hệ trẻ của G1.
Đáp án đúng: C

Câu 46: Khi bật JDK 26 với G1, nên diễn giải cải tiến JEP 522 thế nào?
A. Bảo đảm mọi workload đều chạy nhanh gấp đôi.
B. Kỳ vọng throughput tăng, nhưng cần đo trên workload.
C. Bảo đảm không còn cạnh tranh CPU với GC threads.
D. Bảo đảm mọi pause time giảm xuống bằng không.
Đáp án đúng: B

Câu 47: JEP 500 trong JDK 26 làm gì với việc sửa field `final` qua deep reflection?
A. Mặc định chặn mọi thao tác gán lại và ném lỗi ngay.
B. Phát cảnh báo để chuẩn bị cho hạn chế trong tương lai.
C. Cho phép sửa field `final` hoàn toàn không cảnh báo.
D. Tự chuyển mọi trường `final` thành trường mutable.
Đáp án đúng: B

Câu 48: Khi virtual thread đợi thread khác khởi tạo class trong JDK 26, thay đổi nào giúp giảm pinning?
A. Thường unmount khỏi carrier trong lúc chờ.
B. Tự chuyển class initializer sang tác vụ native.
C. Thường giữ carrier bị pin cho tới khi hết chờ.
D. Tự tăng số carrier lên vô hạn để tránh chờ.
Đáp án đúng: A
