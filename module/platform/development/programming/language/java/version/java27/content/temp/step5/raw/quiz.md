Câu 1: JDK 27 được phát hành chính thức vào ngày nào?
A. Ngày 15 tháng 3 năm 2027 theo lịch Java.
B. Ngày 16 tháng 9 năm 2025 theo lịch Java.
C. Ngày 15 tháng 9 năm 2026 theo lịch Java.
D. Ngày 17 tháng 3 năm 2026 theo lịch Java.
Đáp án đúng: C

Câu 2: Trong chu kỳ Java SE, JDK 27 thuộc nhóm phát hành nào?
A. Bản LTS mới, thay thế nhánh Java 25.
B. Bản thử nghiệm nội bộ trước Java 25.
C. Bản vá CPU cho Java 26 đã ra mắt.
D. Một feature release không phải LTS.
Đáp án đúng: D

Câu 3: JDK 27 gồm bao nhiêu JEP, với phân loại preview/incubator ra sao?
A. 9 JEP: bốn preview và một incubator.
B. 8 JEP: ba preview và hai incubator.
C. 9 JEP: một preview và bốn incubator.
D. 10 JEP: hai preview và ba incubator.
Đáp án đúng: A

Câu 4: Khi cần xem chính xác patch build JDK 27 đang dùng, nên kiểm tra gì?
A. Chỉ xem manifest trong thư viện ứng dụng.
B. Chạy java -version trên JDK thực tế đang chạy.
C. Chỉ đọc sourceCompatibility trong build script.
D. Dùng javac -help trên máy của nhà phát triển.
Đáp án đúng: B

Câu 5: Biên dịch bằng JDK 27 với --release 25 có ý nghĩa nào?
A. Vẫn cho dùng trực tiếp toàn bộ API Java 27.
B. Tự bật tất cả tính năng preview của Java 27.
C. Giới hạn API và class file theo Java 25.
D. Tự hạ runtime đang chạy về phiên bản 25.
Đáp án đúng: C

Câu 6: Class file được javac tạo theo target Java 27 có major version nào?
A. Major version 71 theo quy tắc class file Java.
B. Major version 70 tương ứng với JDK 26.
C. Major version 69 tương ứng với JDK 25.
D. Major version 67 tương ứng với JDK 23.
Đáp án đúng: A

Câu 7: Để biên dịch mã dùng preview ngôn ngữ của JDK 27 cần gì?
A. Chỉ thêm module jdk.incubator.vector là đủ.
B. Bật --enable-preview cùng mức release 27.
C. Chỉ dùng target bytecode 26 không cần cờ.
D. Chỉ đặt --source 25 không cần cờ khác.
Đáp án đúng: B

Câu 8: Chạy class dùng preview của JDK 27 cần xử lý điều kiện nào?
A. Bắt buộc khai báo tất cả package là open.
B. Runtime phù hợp và bật --enable-preview.
C. Chỉ cần chọn G1 làm garbage collector.
D. JVM tự chạy preview trên mọi bản Java cũ.
Đáp án đúng: B

Câu 9: JEP 523 thay đổi lựa chọn GC mặc định của HotSpot theo hướng nào?
A. G1 được chọn khi không chỉ định collector.
B. Parallel được chọn cố định cho mọi container.
C. ZGC được chọn thay G1 cho mọi ứng dụng.
D. Serial được chọn ở mọi môi trường mặc định.
Đáp án đúng: A

Câu 10: Điểm mới của G1 default trong JDK 27 ảnh hưởng tới môi trường nào?
A. Chỉ tiến trình chạy trên máy có GPU rời.
B. Cả nơi trước kia HotSpot có thể chọn Serial.
C. Chỉ ứng dụng có module-info.java riêng.
D. Chỉ chương trình dùng Project Reactor và Netty.
Đáp án đúng: B

Câu 11: Nếu ứng dụng đã đặt -XX:+UseSerialGC thì JEP 523 quyết định thế nào?
A. G1 buộc thay Serial dù đã chỉ định flag.
B. Giữ SerialGC nếu đã chọn bằng flag.
C. JVM từ chối khởi động vì cờ GC cũ.
D. JDK luôn đổi sang ZGC khi heap đủ nhỏ.
Đáp án đúng: B

Câu 12: Muốn chọn G1 tường minh trên HotSpot, cờ nào phù hợp?
A. -XX:+UseG1GC để chọn G1 làm collector.
B. -XX:+UseSerialGC để chọn G1 làm collector.
C. -XX:+UseParallelGC để chọn G1 làm collector.
D. -XX:+UseZGC để chọn G1 làm collector.
Đáp án đúng: A

Câu 13: Khi nâng cấp lên JDK 27, cách nào xác nhận collector thực tế?
A. Đo số dòng import của ứng dụng Java.
B. Xem log -Xlog:gc hoặc thông tin VM GC.
C. Đếm số class nằm trong runtime image.
D. Xem nội dung pom.xml mà không chạy JVM.
Đáp án đúng: B

Câu 14: Khi so sánh G1 với ZGC trên cùng ứng dụng, nên đo những gì?
A. Chỉ thời gian tạo HTML từ Javadoc.
B. Độ trễ, throughput, CPU và bộ nhớ thực.
C. Chỉ số lượng class trong Java source code.
D. Chỉ số lượng dependency trong Gradle.
Đáp án đúng: B

Câu 15: Một JVM container trước kia tự chọn Serial, nay chạy JDK 27; điều gì cần thử?
A. Đo lại startup, footprint và độ trễ với G1.
B. Giữ nguyên các giả định Serial mà không đo.
C. Bỏ toàn bộ bộ nhớ heap để dùng native.
D. Buộc đổi sang ZGC cho mọi workload nhỏ.
Đáp án đúng: A

Câu 16: Phát biểu nào đúng về phạm vi tính năng G1 default của JDK 27?
A. Thay mặc định HotSpot, không đổi ngôn ngữ.
B. Là lớp mới trong java.lang.classfile.
C. Là từ khóa mới thay cho biểu thức switch.
D. Là API preview phải bật khi biên dịch source.
Đáp án đúng: A

Câu 17: JEP 534 làm compact object headers thành mặc định nhằm mục tiêu nào?
A. Bỏ nhu cầu garbage collection trong JVM.
B. Giảm chi phí header và cải thiện mật độ heap.
C. Đổi mọi đối tượng thành bản ghi bất biến.
D. Thay toàn bộ object Java bằng primitive value.
Đáp án đúng: B

Câu 18: Trên hệ 64 bit, compact object header của HotSpot giảm từ mức nào xuống mức nào?
A. Từ 256 bit xuống 128 bit cho header đối tượng.
B. Từ 128 bit xuống 16 bit cho header đối tượng.
C. Từ 96 bit xuống 64 bit cho header đối tượng.
D. Từ 64 bit xuống 32 bit cho header đối tượng.
Đáp án đúng: C

Câu 19: Compact object headers mặc định của JDK 27 tác động trực tiếp phần nào?
A. Bố cục header của object do HotSpot quản lý.
B. Tên method và kiểu trả về trong Java source.
C. Mã hóa UTF-8 của nội dung Java String.
D. Định dạng thông điệp TCP của HttpClient.
Đáp án đúng: A

Câu 20: Một lớp Java có nhiều object nhỏ sau khi bật compact headers có thể hưởng lợi gì?
A. Giảm footprint và tăng locality trong heap.
B. Tự loại bỏ mọi lần gọi equals runtime.
C. Tự nén mọi byte array còn một byte.
D. Tự biến class thường thành Java record.
Đáp án đúng: A

Câu 21: Tính năng compact headers mặc định được mô tả cho kiến trúc nào?
A. Mọi JVM nhúng 8 bit không có ngoại lệ.
B. Chỉ JVM có GPU để xử lý vector dữ liệu.
C. Chỉ các JVM chạy bằng kiến trúc JavaScript.
D. HotSpot 64 bit theo phạm vi của JEP 534.
Đáp án đúng: D

Câu 22: Nếu header gọn hơn 32 bit, có thể kết luận mọi object giảm đúng bốn byte RAM không?
A. Có, mọi object giảm đúng bốn byte heap.
B. Không, vì mọi object đều ở native memory.
C. Có, toàn bộ heap luôn giảm đúng 33 phần trăm.
D. Không, còn alignment và bố cục từng object.
Đáp án đúng: D

Câu 23: Compact headers có làm thay đổi hợp đồng equals và hashCode của object không?
A. Không; ngữ nghĩa API vẫn theo hợp đồng Java.
B. Có; hashCode được đổi thành địa chỉ vật lý.
C. Không; JVM cấm gọi equals khi GC hoạt động.
D. Có; hai object có chung header sẽ bằng nhau.
Đáp án đúng: A

Câu 24: Muốn đo hiệu quả compact headers ở ứng dụng nhiều object nhỏ, nên làm gì?
A. Chỉ thay kích thước mã nguồn trong JAR.
B. Benchmark heap, allocation và GC thực tế.
C. Chỉ chạy doclint để suy ra mức sử dụng heap.
D. Chỉ đếm số dòng thuộc file Java source.
Đáp án đúng: B

Câu 25: Khẳng định nào về compact headers và G1 ở Java 27 là đúng?
A. Chỉ làm thay đổi tên GC trong startup log.
B. Đây là cùng một JEP và cùng một cơ chế.
C. G1 và compact headers là hai thay đổi riêng.
D. Chỉ hoạt động khi ứng dụng bật preview compiler.
Đáp án đúng: C

Câu 26: JEP 527 đưa khả năng nào vào bảo mật kết nối TLS 1.3?
A. Trao đổi khóa hybrid trong TLS 1.3.
B. Thay TLS 1.3 bằng giao thức TCP mới.
C. Chỉ hỗ trợ chữ ký số RSA cổ điển.
D. Bỏ mọi thuật toán xác thực chứng chỉ TLS.
Đáp án đúng: A

Câu 27: Trao đổi khóa hybrid trong JDK 27 kết hợp hai họ cơ chế nào?
A. ECDHE cổ điển được kết hợp với ML-KEM.
B. AES-GCM với thuật toán băm SHA-256.
C. ECDSA và RSA như hai chữ ký chứng thư.
D. RSA-PSS cùng thuật toán băm SHA-512.
Đáp án đúng: A

Câu 28: Tính năng hybrid key exchange của JDK 27 áp dụng cho TLS phiên bản nào?
A. TLS 1.1 là giao thức duy nhất có hiệu lực.
B. TLS 1.0 được bật lại theo mặc định.
C. SSL 3.0 được Java 27 phục hồi hỗ trợ.
D. TLS 1.3 được tích hợp trong SunJSSE.
Đáp án đúng: D

Câu 29: Named group hybrid nào được SunJSSE ưu tiên mặc định trên JDK 27?
A. SecP384r1MLKEM1024 mặc định đứng đầu.
B. ffdhe2048MLKEM256 mặc định đứng đầu.
C. X25519MLKEM768 được ưu tiên mặc định.
D. SecP256r1MLKEM768 mặc định đứng đầu.
Đáp án đúng: C

Câu 30: Named group nào khác X25519MLKEM768 cũng được hỗ trợ trong JDK 27?
A. AES256MLKEM512 là nhóm trao đổi khóa chuẩn.
B. X448MLKEM256 là nhóm mặc định bắt buộc.
C. RSA2048MLKEM256 là nhóm được hỗ trợ sẵn.
D. SecP256r1MLKEM768 là một nhóm được hỗ trợ.
Đáp án đúng: D

Câu 31: Named group nào kết hợp secp384r1 với ML-KEM-1024?
A. SecP384r1MLKEM768 là nhóm đã được bật sẵn.
B. SecP384r1MLKEM1024 thuộc nhóm hybrid hỗ trợ.
C. X25519MLKEM768 là nhóm có đường cong này.
D. SecP256r1MLKEM768 là nhóm có cấu hình này.
Đáp án đúng: B

Câu 32: Khi ứng dụng Java 27 kết nối peer không hỗ trợ nhóm hybrid, điều gì đúng?
A. Mọi kết nối TLS 1.3 đều buộc dùng hybrid.
B. SunJSSE sẽ tự bật lại giao thức SSL 3.0.
C. JVM tự thay chữ ký số bằng giao thức UDP.
D. Không thể khẳng định handshake dùng hybrid.
Đáp án đúng: D

Câu 33: Ứng dụng dùng javax.net.ssl trên JDK 27 hưởng cải tiến nào mà không đổi code?
A. Có thể thương lượng hybrid nếu peer hỗ trợ.
B. Bắt buộc bỏ mọi cấu hình TLS named group.
C. Tự chuyển toàn bộ chứng thư sang ML-DSA ngay.
D. Tự ngừng xác minh certificate của đối tác.
Đáp án đúng: A

Câu 34: Thuộc tính hệ thống nào được dùng cấu hình TLS named groups trong Java?
A. java.net.useSystemProxies cho danh sách nhóm.
B. jdk.tls.namedGroups cho cấu hình named groups.
C. java.security.namedPackages cho danh sách nhóm.
D. jdk.http.auth.tunneling cho danh sách nhóm.
Đáp án đúng: B

Câu 35: API nào cho phép đặt named groups theo từng cấu hình kết nối TLS?
A. SSLEngine.setRemoteTypes với danh sách nhóm.
B. Dùng SSLParameters.setNamedGroups(...) để chọn.
C. KeyStore.setTlsGroups với danh sách nhóm.
D. SSLContext.setDefaultGroups với danh sách nhóm.
Đáp án đúng: B

Câu 36: Muốn kiểm tra handshake thực sự đã chọn nhóm hybrid, cách nào hữu ích?
A. Chỉ đọc header HTTP Content-Type từ client.
B. Chỉ kiểm tra biến JAVA_HOME trên server.
C. Xem key_share trong JSSE handshake debug.
D. Chỉ nhìn đuôi .pem của chứng thư máy chủ.
Đáp án đúng: C

Câu 37: Hybrid key exchange của JDK 27 có tự thay đổi xác thực chứng chỉ số không?
A. Không, vì TLS 1.3 không dùng chứng chỉ.
B. Có, tất cả chứng chỉ RSA bị tự động xóa.
C. Không, key exchange khác xác thực chứng chỉ.
D. Có, mọi certificate phải chuyển sang ML-KEM.
Đáp án đúng: C

Câu 38: Lợi ích bảo mật chính của hybrid TLS key exchange là gì?
A. Ngăn mọi tấn công mật khẩu và mã độc runtime.
B. Đảm bảo loại bỏ mọi tấn công ứng dụng web.
C. Thay thế quyền phân quyền của Java SecurityManager.
D. Giảm rủi ro giải mã dữ liệu thu hôm nay về sau.
Đáp án đúng: D

Câu 39: Nếu dùng JSSE provider tùy biến, cần kiểm tra gì khi nâng JDK 27?
A. Kiểm tra provider và peer hỗ trợ hybrid.
B. Chỉ chỉnh -Xmx rồi đo kích thước heap.
C. Chỉ sửa tên module-info để bật TLS 1.3.
D. Chỉ kiểm tra chuỗi phiên bản Java trên IDE.
Đáp án đúng: A

Câu 40: JEP 536 tăng cường JFR bằng khả năng nào?
A. Xóa toàn bộ sự kiện JFR sau một giây.
B. Mã hóa mọi file log ứng dụng bằng mật khẩu JVM.
C. JFR che dữ liệu nhạy cảm ngay trong JVM.
D. Thay tất cả thread dump thành file PDF.
Đáp án đúng: C

Câu 41: Những loại dữ liệu nào nằm trong phạm vi redaction được JEP 536 nhắc tới?
A. Toàn bộ nội dung response HTTP của ứng dụng.
B. Tất cả mã nguồn và bytecode được JVM tải.
C. Tất cả bản ghi giao dịch trong cơ sở dữ liệu.
D. Đối số lệnh và giá trị khởi tạo env và properties.
Đáp án đúng: D

Câu 42: Thời điểm thực hiện JFR in-process redaction của Java 27 là khi nào?
A. Trước khi dữ liệu JFR rời khỏi tiến trình.
B. Sau khi file đã được gửi lên dịch vụ cloud.
C. Sau khi người dùng tải file JFR về máy.
D. Chỉ khi dashboard bên ngoài mở recording.
Đáp án đúng: A

Câu 43: JFR redaction mặc định có nghĩa tất cả sự kiện tùy biến cũng được lọc không?
A. Có, mọi trường String đều bị thay bằng sao.
B. Có, JFR tự dò toàn bộ thông tin bí mật.
C. Không; phạm vi lọc bị giới hạn theo event.
D. Không, vì redaction chỉ dành cho TLS socket.
Đáp án đúng: C

Câu 44: Muốn xem các bộ lọc JFR redaction đang có, tùy chọn nào phù hợp?
A. Dùng -XX:+UseZGC để xem bộ lọc dữ liệu.
B. Dùng -Xdoclint để xem bộ lọc môi trường.
C. Dùng --enable-preview để xem thiết lập JFR.
D. -XX:FlightRecorderOptions:help liệt kê các thiết lập.
Đáp án đúng: D

Câu 45: Khi tên biến môi trường nhạy cảm chưa khớp mặc định, nên làm gì?
A. Bật trace SQL để tìm lại biến môi trường.
B. Tắt mọi JFR event để bỏ qua thao tác giám sát.
C. Bổ sung redact-key filter cho biến nhạy cảm.
D. Chuyển toàn bộ dữ liệu sang Unicode UTF-16.
Đáp án đúng: C

Câu 46: Thuộc tính đỏ hóa đối số dòng lệnh JFR có tên nào?
A. redact-argument trong FlightRecorderOptions.
B. redact-source trong FlightRecorderOptions.
C. redact-memory trong FlightRecorderOptions.
D. redact-threads trong FlightRecorderOptions.
Đáp án đúng: A

Câu 47: JFR redaction có thay thế quản lý quyền truy cập recording không?
A. Có, JVM tự mã hóa mọi file JFR trước khi xuất.
B. Có, bản ghi đã che thì công khai an toàn tuyệt đối.
C. Không, JFR không có dữ liệu gì về tiến trình.
D. Không, file JFR vẫn cần bảo vệ truy cập.
Đáp án đúng: D

Câu 48: JEP 536 cho phép bảo vệ dữ liệu nào liên quan JVM system properties?
A. Mọi tệp properties được đóng gói trong JAR.
B. Mọi thay đổi sau khởi động trong mọi event tùy biến.
C. Giá trị ban đầu phù hợp bộ lọc nhạy cảm của JFR.
D. Mọi chuỗi thuộc System.out của tiến trình.
Đáp án đúng: C

Câu 49: Dùng JFR redaction để bảo vệ log ứng dụng thông thường có đúng không?
A. Có, JFR tự thay nội dung response HTTP.
B. Không, log ứng dụng cần cơ chế lọc riêng biệt.
C. Có, logger buộc đọc cấu hình JFR trước khi ghi.
D. Có, JFR tự viết lại tất cả file log4j ngoài JVM.
Đáp án đúng: B

Câu 50: Công cụ chẩn đoán nào trên JDK 27 có lệnh VM.security_properties?
A. javadoc cho phép sửa thuộc tính bảo mật của JVM.
B. jshell cho phép tạo các recording JFR tự động.
C. jcmd có lệnh VM.security_properties để xem.
D. jlink cho phép tải tên miền qua TLS 1.3.
Đáp án đúng: C

Câu 51: Thay đổi định dạng JSON thread dump được nhắc đến trên JDK 27 là gì?
A. Các định danh và bộ đếm chính được xuất dạng số JSON.
B. Mọi tên thread được ghi thành đối tượng bytecode.
C. Mọi số đếm được đổi thành chuỗi bất kể loại.
D. Tất cả stack trace bị chuyển thành binary JFR.
Đáp án đúng: A

Câu 52: Bash completion cho jcmd từ JDK 27 giúp ích điều gì?
A. Tự thực thi mọi jcmd ở cấp quyền administrator.
B. Tự thay đổi mức log GC trong runtime.
C. Gợi ý lệnh và tham số jcmd trong Bash shell.
D. Tự chuyển mọi thread dump thành file HTML.
Đáp án đúng: C

Câu 53: Java 27 cập nhật FFM API để hỗ trợ gì trước native downcall?
A. Tự đóng mọi MemorySegment trước downcall.
B. Đặt execution state trước native downcall.
C. Tự tải tên hàm C qua DNS lookup runtime.
D. Tự sinh Java source từ mọi thư viện native.
Đáp án đúng: B

Câu 54: Lazy Constants trong JDK 27 hiện có trạng thái gì?
A. Incubator module đầu tiên của JDK 27.
B. Bị gỡ khỏi JDK trong bản 27 chính thức.
C. Đã chuẩn hóa và không cần preview khi biên dịch.
D. Third Preview của Lazy Constants ở JDK 27.
Đáp án đúng: D

Câu 55: Với LazyConstant.of và get, hành vi nào được API preview mô tả?
A. Giá trị được đặt lại khi tăng số thread.
B. Giá trị được tạo ngay lúc gọi factory of.
C. Giá trị được tính lại khi mỗi lần gọi get.
D. Giá trị được tính khi get đầu tiên và giữ bất biến.
Đáp án đúng: D

Câu 56: Tính năng Primitive Types in Patterns của JDK 27 đang ở trạng thái nào?
A. Twelfth Incubator trong module Vector API.
B. Chỉ là công cụ phân tích Javadoc Markdown.
C. Fifth Preview trong JDK 27 cho patterns.
D. Đã ổn định hoàn toàn kể từ Java 21 LTS.
Đáp án đúng: C

Câu 57: Mục tiêu của primitive patterns preview là gì?
A. Tự boxing mọi phép toán số học theo mặc định.
B. Hỗ trợ primitive trong instanceof và switch.
C. Thay enum và record bằng chuỗi ký tự.
D. Bỏ hoàn toàn các kiểu primitive của ngôn ngữ.
Đáp án đúng: B

Câu 58: Structured Concurrency ở Java 27 thuộc giai đoạn nào?
A. API đã ổn định trong java.base từ Java 17.
B. Tính năng chỉ bật qua ứng dụng HTTP server.
C. Incubator đời đầu của một module JVM.
D. Seventh Preview, chưa phải API ổn định cuối cùng.
Đáp án đúng: D

Câu 59: Ý tưởng chính của Structured Concurrency preview là gì?
A. Buộc mọi task đều chạy ở cùng một CPU core.
B. Bỏ toàn bộ khả năng chạy đồng thời trong JVM.
C. Quản lý các task liên quan như một đơn vị công việc.
D. Tạo thread riêng không có cơ chế hủy hoặc join.
Đáp án đúng: C

Câu 60: Vector API thuộc trạng thái nào trong bản phát hành Java 27?
A. Bộ thư viện bị xóa khỏi JDK từ Java 26.
B. API ổn định đã vào java.base từ Java 23.
C. Incubator lần thứ mười hai, chưa là API ổn định.
D. Preview cú pháp switch của ngôn ngữ Java.
Đáp án đúng: C

Câu 61: Module của Vector API trong JDK 27 có tên nào?
A. jdk.crypto.vector chuyên mã hóa khóa TLS.
B. java.lang.vector chứa tất cả mẫu dữ liệu.
C. java.nio.gpu là module vector mặc định.
D. jdk.incubator.vector dùng cho phép toán vector.
Đáp án đúng: D

Câu 62: Vector API trên CPU khác nhau được dùng theo cách nào?
A. Chỉ chạy trên một hệ điều hành cụ thể.
B. Bắt JVM chuyển toàn bộ tính toán sang GPU.
C. Buộc mọi CPU phải có cùng độ rộng SIMD.
D. Dựa vào khả năng vector của CPU và tối ưu JIT.
Đáp án đúng: D

Câu 63: PEM Encodings of Cryptographic Objects ở JDK 27 thuộc giai đoạn nào?
A. Twelfth Incubator chung module Vector API.
B. Third Preview, chưa phải API ổn định vĩnh viễn.
C. Tính năng hoàn chỉnh lần đầu từ Java 17.
D. Tính năng bị loại bỏ trước khi Java 27 phát hành.
Đáp án đúng: B

Câu 64: API PEM preview ở JDK 27 nhắm tới những đối tượng nào?
A. Object heap, thread dump và luồng thực thi.
B. Khóa mật mã, chứng chỉ và danh sách thu hồi chứng chỉ.
C. Class file, module descriptor và Java package.
D. Giao dịch SQL, bảng dữ liệu và chỉ mục.
Đáp án đúng: B

Câu 65: Nhóm nào gồm đúng các tính năng preview trong chín JEP Java 27?
A. Lazy, primitive patterns, structured concurrency, PEM.
B. G1 default, Vector API, compact headers, PEM.
C. TLS hybrid, Class-File API, Javadoc Markdown, ZGC.
D. G1 default, compact headers, TLS hybrid, JFR redaction.
Đáp án đúng: A

Câu 66: Trong số chín JEP của Java 27, tính năng nào là incubator?
A. TLS 1.3 hỗ trợ trao đổi khóa hybrid.
B. JFR redaction chạy ngay trong tiến trình.
C. G1 làm collector mặc định cho HotSpot.
D. Vector API tiếp tục giai đoạn ươm tạo API.
Đáp án đúng: D

Câu 67: Đội nâng cấp từ Java 25 LTS lên 27 nên xác minh điểm nào trước khi deploy?
A. Chỉ tổng số comment của source và tài liệu.
B. Chỉ lượng file JAR được sao chép sang server.
C. Chỉ số phiên bản IDE và định dạng tên lớp Java.
D. Ma trận API, GC, TLS, JFR và hiệu năng trên tải thật.
Đáp án đúng: D

Câu 68: Muốn sử dụng module Vector API incubator ở JDK 27, điều kiện nào cần xét?
A. Chỉ bật -Xlog:gc mà không cần module tương ứng.
B. Chỉ thêm chú thích Markdown vào source của project.
C. Thêm module jdk.incubator.vector khi build và chạy.
D. Chỉ đổi giao thức TLS 1.3 sang HTTP/2 khi khởi động.
Đáp án đúng: C
