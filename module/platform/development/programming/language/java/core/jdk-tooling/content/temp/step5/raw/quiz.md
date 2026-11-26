Câu 1. Trong lệnh javac -d out src/App.java, tùy chọn -d out có vai trò gì?
A. Đặt thư mục gốc để ghi class file đã biên dịch
B. Đặt nơi ghi file Java nguồn do annotation processor tạo
C. Đặt classpath để tìm các thư viện runtime bên ngoài
D. Đặt module path cho các module đã được đóng gói
Đáp án đúng: A

Câu 2. Khi cần biên dịch nhắm Java 17, javac --release 17 giúp kiểm soát gì?
A. Chỉ mức cú pháp nhưng vẫn cho gọi API JDK mới hơn
B. Chỉ bản class file mà không kiểm tra API Java được dùng
C. Chỉ phiên bản JRE sẽ tự cài trên máy chạy ứng dụng
D. Khóa cú pháp, class version và API JDK theo Java 17
Đáp án đúng: D

Câu 3. Trong javac, -classpath deps.jar dùng chủ yếu để làm gì?
A. Tìm class và JAR phụ thuộc qua classpath chỉ định
B. Chỉ thư mục xuất class file để công cụ jar đóng gói
C. Chỉ đường dẫn tới mã nguồn Java sẽ biên dịch đầu vào
D. Chỉ keystore dùng cho chứng chỉ của thư viện runtime
Đáp án đúng: A

Câu 4. Khi biên dịch module Java có requires tới module khác, tùy chọn nào chỉ nơi tìm module phụ thuộc?
A. --source-path để tự đặt module name cho mọi thư viện
B. Dùng --module-path cho các named module phụ thuộc
C. --processor-path để nạp module runtime vào JVM
D. --boot-class-path để chỉ module dependencies từ Maven
Đáp án đúng: B

Câu 5. Với mã nguồn có ký tự tiếng Việt, javac -encoding UTF-8 phục vụ việc gì?
A. Quy định charset mặc định cho mọi socket của ứng dụng
B. Ép mọi String runtime được lưu theo UTF-8 trên heap
C. Quy định cách giải mã bytes của tệp nguồn Java
D. Chuyển đầu ra .class sang dạng văn bản UTF-8
Đáp án đúng: C

Câu 6. Khi muốn reflection đọc được tên tham số method từ bytecode, nên dùng tùy chọn javac nào?
A. Dùng -g:none để khôi phục tên tham số từ call stack
B. Dùng -parameters để giữ metadata tên tham số method
C. Dùng -Xlint:all để thêm tên tham số vào constant pool
D. Dùng -encoding để ghi tham số theo charset hiện tại
Đáp án đúng: B

Câu 7. javac -Xlint:unchecked chủ yếu kích hoạt điều gì?
A. Báo lỗi bắt buộc cho mọi biến chưa khởi tạo bằng null
B. Bật cảnh báo unchecked liên quan đến generic type
C. In thông số heap của JVM lúc compiler bắt đầu chạy
D. Tắt toàn bộ annotation processing trên classpath
Đáp án đúng: B

Câu 8. Khi dùng javac @sources.args, dấu @ cho phép làm gì?
A. Đọc danh sách đối số compiler từ tệp sources.args
B. Biên dịch annotation tên sources.args trong mã nguồn
C. Đưa sources.args thành module được chạy bởi java -m
D. Tự tạo JAR tên sources.args từ đầu vào compiler
Đáp án đúng: A

Câu 9. Tùy chọn javac -processor com.acme.Apt thích hợp để làm gì?
A. Chỉ định lớp main dùng cho java -jar sau khi compile
B. Chỉ định implementation của Security Provider trong JDK
C. Chọn annotation processor com.acme.Apt cho lần compile
D. Chỉ định class chứa các bytecode verifier của JVM
Đáp án đúng: C

Câu 10. Muốn xem bytecode instruction của method trong một .class, công cụ nào phù hợp?
A. javac -d in bytecode trước khi ghi class file vào out
B. javadoc -d disassemble bytecode đã có trong class file
C. jpackage --input in chỉ thị JVM in mọi bytecode
D. Dùng javap -c để đọc bytecode instruction của class
Đáp án đúng: D

Câu 11. Khi chạy một main class không dùng module, java -cp có chức năng nào?
A. Đặt thư mục nguồn để javac đọc và biên dịch tự động
B. Đặt đường dẫn JAR nhận được từ class loader bootstrap
C. Đặt đường tìm class và JAR trước tên main class
D. Đặt vị trí file cấu hình keytool cho tiến trình runtime
Đáp án đúng: C

Câu 12. java -jar app.jar thường xác định main class qua đâu?
A. Tệp module-info.java nằm trong thư mục source của JAR
B. Thuộc tính Main-Class trong manifest của JAR thực thi
C. Tên package của .class đầu tiên theo thứ tự ZIP entry
D. Thuộc tính Implementation-Version trong manifest
Đáp án đúng: B

Câu 13. Với java -Dapp.mode=test com.acme.Main, -D làm gì?
A. Đặt biến môi trường hệ điều hành có tên app.mode
B. Biên dịch lại main class bằng flag debug của javac
C. Đặt system property app.mode=test cho JVM hiện tại
D. Đặt chương trình chạy bằng user Linux tên test
Đáp án đúng: C

Câu 14. Trong lệnh java -ea com.acme.Main, -ea có hiệu ứng nào?
A. Bật kiểm tra câu lệnh assert cho các lớp ứng dụng
B. Bật Java agent và gọi premain của class Main
C. Bật cơ chế Java Flight Recorder trong thời gian cố định
D. Bật JVM logging của GC sang mức warning
Đáp án đúng: A

Câu 15. Khi muốn chạy lớp main trong named module, cú pháp nào phù hợp nếu module đã có trên module path?
A. java --module shop.app/com.acme.Main để chỉ module và lớp
B. java --class-path shop.app/com.acme.Main để chỉ module
C. java --release shop.app/com.acme.Main để bật module
D. java -jar shop.app/com.acme.Main để chọn class nội bộ
Đáp án đúng: A

Câu 16. Công cụ jshell phù hợp nhất cho tình huống nào?
A. Tạo installer cho Java desktop app mà không cần mã nguồn
B. Thử biểu thức Java trực tiếp trong phiên REPL jshell
C. Phân tích deadlock của một JVM đang chạy bằng thread dump
D. Cắt giảm module của runtime image trước khi đóng gói
Đáp án đúng: B

Câu 17. Trong jshell, lệnh /vars có tác dụng gì?
A. Liệt kê các module phụ thuộc được tìm bởi jdeps
B. Liệt kê các luồng đang chạy trong JVM mục tiêu
C. Liệt kê các entry certificate của keystore mặc định
D. Liệt kê biến đã khai trong phiên jshell hiện tại
Đáp án đúng: D

Câu 18. Khi đã có tệp thử nghiệm snippets.jsh, lệnh jshell nào nạp nội dung tệp?
A. Dùng /save snippets.jsh để thực thi lại mã đã lưu
B. Dùng /list snippets.jsh để biên dịch mô-đun từ tệp
C. Dùng /open snippets.jsh để nạp và chạy các snippet
D. Dùng /set snippets.jsh để nối classpath runtime
Đáp án đúng: C

Câu 19. jar --create --file app.jar -C out . thường có kết quả gì?
A. Tạo app.jar chỉ chứa tên thư mục out, không chứa class file
B. Chạy main class trong out rồi lưu output thành app.jar
C. Tạo app.jar từ thư mục out với cấu trúc entry tương ứng
D. Tạo custom JVM runtime image dựa trên class file của out
Đáp án đúng: C

Câu 20. Cần xem danh sách entry bên trong app.jar mà không giải nén; dùng lệnh nào?
A. jar --list --file app.jar để liệt kê nội dung archive
B. jar --extract --file app.jar để liệt kê mà không giải nén
C. jar --update --file app.jar để in danh sách rồi thoát
D. jar --create --file app.jar để đọc manifest không sửa JAR
Đáp án đúng: A

Câu 21. Muốn giải nén các entry của app.jar vào thư mục hiện tại, tùy chọn jar nào đúng?
A. jar --describe-module --file app.jar để trích file
B. jar --list --file app.jar để chép file ra thư mục
C. jar --create --file app.jar để khôi phục tệp gốc
D. Giải nén entry bằng jar --extract --file app.jar
Đáp án đúng: D

Câu 22. Trong jar --create, --main-class com.acme.Main thường được dùng cho mục đích gì?
A. Đặt module name được dùng bởi jlink khi tạo image
B. Đặt tên lớp của annotation processor trên classpath
C. Ghi entry point Main-Class trong manifest của JAR
D. Chọn Java runtime phiên bản nhỏ nhất cho app.jar
Đáp án đúng: C

Câu 23. Khi cần thêm hoặc thay thế entry trong app.jar đã tồn tại, tùy chọn jar nào phù hợp?
A. jar --update --file app.jar để thêm hoặc thay entry
B. jar --extract --file app.jar để tự động ghi lại entry
C. jar --list --file app.jar rồi class file sẽ đổi theo
D. jar --describe-module --file app.jar để ghi lại ZIP
Đáp án đúng: A

Câu 24. Để multi-release JAR có class riêng cho Java 17, cách bố trí nào đúng?
A. Class phiên bản 17 dưới META-INF/modules/17 và manifest Version: 17
B. Class phiên bản 17 dưới BOOT-INF/classes/17 và manifest Main-Class: 17
C. Class phiên bản 17 dưới META-INF/services/17 và manifest Automatic-Module-Name: 17
D. Class phiên bản 17 dưới META-INF/versions/17 và manifest Multi-Release: true
Đáp án đúng: D

Câu 25. Muốn xem tóm tắt các phụ thuộc tĩnh của app.jar bằng jdeps, tùy chọn nào phù hợp?
A. jdeps --generate-module-info app.jar để in heap usage
B. jdeps --summary app.jar in tóm tắt các phụ thuộc
C. jdeps --list-deps app.jar để tạo native installer
D. jdeps --check app.jar để chạy bytecode unit test
Đáp án đúng: B

Câu 26. jdeps --print-module-deps app.jar có thể hỗ trợ jlink ở điểm nào?
A. Tự tạo runtime image và giải phóng bộ nhớ JVM hiện tại
B. In danh sách bytecode instruction của main class trong JAR
C. Tự cài đặt module thiếu vào JDK đang dùng để biên dịch
D. In tên module phụ thuộc để dùng làm đầu vào --add-modules
Đáp án đúng: D

Câu 27. Khi nghi ứng dụng dùng các API nội bộ JDK không được hỗ trợ, jdeps có tùy chọn nào?
A. jdeps --jdk-internals tìm tham chiếu API JDK nội bộ
B. Dùng --strip-debug để tìm các API JDK private đang gọi
C. Dùng --main-class để tìm API nội bộ qua manifest entry
D. Dùng --exportcert để quét khóa nội bộ trong JAR
Đáp án đúng: A

Câu 28. Giới hạn nào của phân tích phụ thuộc tĩnh bằng jdeps cần chú ý?
A. Luôn xác định được mọi tên class tạo bằng Class.forName từ input
B. Tự chạy chương trình để khám phá module được tải lúc runtime
C. Có thể không phát hiện class chỉ được tải động bằng reflection
D. Tự kiểm chứng các endpoint mạng được gọi bằng HttpClient
Đáp án đúng: C

Câu 29. jlink --module-path mods --add-modules shop.app --output runtime nhằm tạo sản phẩm nào?
A. JAR archive độc lập chứa toàn bộ mã nguồn Java của app
B. Bộ cài đặt .msi cho mọi hệ điều hành từ một lệnh
C. Thread dump dạng văn bản từ JVM đang thực thi
D. Tạo runtime image từ module ứng dụng và các phụ thuộc
Đáp án đúng: D

Câu 30. Trong lệnh jlink, --strip-debug có vai trò chính nào?
A. Loại thông tin debug khỏi runtime image để giảm kích thước
B. Loại mọi module nền tảng không dùng dựa vào runtime profile
C. Tắt assertions của ứng dụng sau khi ảnh runtime được tạo
D. Chuyển mọi class file sang dạng source code không có comment
Đáp án đúng: A

Câu 31. Đặc điểm nào của runtime image tạo bởi jlink cần tính khi phân phối?
A. Image không chứa JVM nên bắt buộc người dùng cài JRE riêng
B. Image chỉ chứa source code và cần javac khi khởi động app
C. Image gắn với nền tảng, không phải gói chạy đa hệ điều hành
D. Image tự biến thành installer hệ điều hành khi chạy lệnh java
Đáp án đúng: C

Câu 32. Khi dùng jpackage --type app-image, đầu ra cơ bản là gì?
A. Một tệp JAR nguồn chứa toàn bộ Java source của ứng dụng
B. Một báo cáo jdeps về các module thiếu trong classpath
C. Thư mục app image chứa launcher và runtime liên quan
D. Một file JFR chứa bản ghi hoạt động thread của JVM
Đáp án đúng: C

Câu 33. Trong jpackage, --runtime-image path được dùng như thế nào?
A. Chỉ thư mục lưu dữ liệu thu thập bởi Java Flight Recorder
B. Dùng runtime image đã chuẩn bị thay cho tạo image mới
C. Chọn thư mục tạm chứa source trước khi gọi compiler
D. Bật tải JRE qua mạng ở lần khởi chạy ứng dụng đầu
Đáp án đúng: B

Câu 34. Khi đóng gói app không modular bằng jpackage, cặp tùy chọn nào mô tả JAR chạy chính?
A. --module-path chỉ main JAR; --add-modules chọn main class
B. --runtime-image chỉ main JAR; --type chọn main class
C. --app-version chỉ main JAR; --name chọn lớp chạy chính
D. --input chỉ thư mục tệp; --main-jar chỉ JAR khởi chạy
Đáp án đúng: D

Câu 35. Với keytool -genkeypair -alias server -keystore store.p12, công việc chính là gì?
A. Sinh key pair và entry chứng chỉ trong keystore
B. Chỉ xuất public certificate đã có sang một file PEM
C. Chỉ nhập certificate CA có sẵn vào truststore hiện tại
D. Chỉ thống kê alias trong keystore mà không tạo key
Đáp án đúng: A

Câu 36. Muốn kiểm tra alias và entry trong keystore đã có, keytool dùng tùy chọn nào?
A. keytool -exportcert -keystore store.p12 để in mọi alias
B. keytool -delete -keystore store.p12 để liệt kê entry
C. keytool -list -keystore store.p12 để xem nội dung kho
D. keytool -genkeypair -keystore store.p12 để quét entry
Đáp án đúng: C

Câu 37. Khi chạy keytool -exportcert -alias server -file cert.cer, thông tin nào được xuất?
A. Private key của alias dưới dạng file PKCS#8 được ký
B. Xuất certificate của alias, không gồm private key
C. Toàn bộ keystore gồm mọi alias và password bảo vệ
D. CSR gửi CA để xin cấp chứng chỉ mới cho alias
Đáp án đúng: B

Câu 38. keytool -importcert thường được dùng trong quy trình nào?
A. Xuất private key từ keystore thành file có mật khẩu
B. Nhập trusted certificate hoặc CA reply vào keystore
C. Sinh trực tiếp một cặp khóa đối xứng dùng cho TLS
D. Chuyển toàn bộ JKS sang native installer của Windows
Đáp án đúng: B

Câu 39. Với keytool -storetype PKCS12, tùy chọn này kiểm soát điều gì?
A. Độ dài private key RSA được tạo bởi -genkeypair
B. Thuật toán hash của tất cả certificate đang được tin
C. Tên provider bắt buộc cho Java Flight Recorder
D. Chọn định dạng keystore PKCS12 khi đọc hoặc ghi
Đáp án đúng: D

Câu 40. jcmd -l thường giúp người vận hành thu thập thông tin gì?
A. Liệt kê các tiến trình JVM cục bộ có thể quan sát
B. Liệt kê mỗi Java class đã được compiler viết ra trên đĩa
C. Liệt kê certificate chain có trong keystore mặc định
D. Liệt kê toàn bộ sự kiện JFR từ tệp recording đã lưu
Đáp án đúng: A

Câu 41. Đối với JVM có PID 1234, jcmd 1234 VM.command_line thường cho biết gì?
A. Danh sách source file chưa được compiler xử lý trong project
B. Thông tin lệnh khởi chạy và tham số JVM của tiến trình đó
C. Danh sách những module không được phân tích bởi jdeps
D. Nội dung của các class file hiện có trong app.jar
Đáp án đúng: B

Câu 42. jcmd 1234 GC.heap_info phù hợp khi cần xem thông tin nào?
A. Tóm tắt trạng thái heap và vùng nhớ quản lý bởi GC
B. Stack trace chi tiết của mỗi thread với monitor bị giữ
C. Danh sách argument dùng bởi annotation processor javac
D. Danh sách event JFR đã ghi ra file trong quá khứ
Đáp án đúng: A

Câu 43. jcmd 1234 Thread.print hỗ trợ việc chẩn đoán nào?
A. Xuất file JAR có manifest cho tiến trình đang chạy
B. Biên dịch lại class bị lỗi và thay bytecode đang chạy
C. Kiểm tra chất lượng chứng chỉ của TLS server đang gọi
D. Lấy thread dump chứa trạng thái và stack của thread
Đáp án đúng: D

Câu 44. Khi nghi deadlock trong JVM đang chạy, jstack 1234 thường cung cấp gì?
A. Báo cáo module dependency được gom từ các JAR ứng dụng
B. Danh sách lệnh JShell được nhập gần đây trong IDE
C. Tệp runtime image được tối ưu theo dữ liệu profiler
D. In stack trace và trạng thái thread để dò deadlock
Đáp án đúng: D

Câu 45. Trong Java Flight Recorder, jcmd 1234 JFR.start name=trace thường thực hiện gì?
A. In ngay bytecode của class trace ra standard output
B. Bắt đầu recording JFR tên trace trong JVM đích
C. Xóa mọi bản ghi JFR cũ và khởi động JVM mới
D. Chỉ chuyển file .jfr thành báo cáo dạng văn bản
Đáp án đúng: B

Câu 46. Nếu JFR recording trace đang hoạt động, jcmd 1234 JFR.dump name=trace filename=trace.jfr làm gì?
A. Bắt buộc dừng recording trước khi có thể xuất dữ liệu
B. Ghi dữ liệu recording hiện có ra tệp trace.jfr
C. Thay toàn bộ stack trace bằng dữ liệu từ jstack
D. Tạo keystore và khóa để ký file JFR trước khi ghi
Đáp án đúng: B

Câu 47. Để xem các sự kiện jdk.CPULoad từ file trace.jfr, cú pháp nào phù hợp?
A. jcmd --events jdk.CPULoad trace.jfr để chạy recording
B. javap -events jdk.CPULoad trace.jfr để in event
C. jfr print --events jdk.CPULoad trace.jfr lọc event
D. jdeps --events jdk.CPULoad trace.jfr để phân tích CPU
Đáp án đúng: C

Câu 48. Để bản dựng Java có tính tái lập cao, bộ thực hành nào đáng ưu tiên?
A. Chỉ bật --release rồi để mọi dependency tự cập nhật mới nhất
B. Chỉ đổi tên artifact qua jar, bỏ qua version runtime dùng build
C. Để JDK tự chọn ngẫu nhiên archive timestamp khi xuất bản
D. Cố định JDK và dependencies; chuẩn hóa input, timestamp
Đáp án đúng: D
