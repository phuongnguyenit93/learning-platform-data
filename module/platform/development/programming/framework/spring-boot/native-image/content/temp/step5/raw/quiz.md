Câu 01. Kết quả chính của GraalVM Native Image khi biên dịch ứng dụng Spring Boot là gì?
A. Image chứa JDK HotSpot để thực thi lệnh `java -jar`
B. Tệp JAR bytecode có thêm cấu hình classpath lúc chạy
C. Bộ mã nguồn Java sinh ra từ toàn bộ Spring bean
D. Binary native cho nền tảng biên dịch đích
Đáp án đúng: D

Câu 02. Spring AOT đóng vai trò gì trong quá trình chuẩn bị ứng dụng cho native build?
A. Sinh mã AOT và gợi ý truy cập khi build
B. Thay thế quy trình kiểm thử bằng bước build image
C. Chuyển các class nghiệp vụ thành file cấu hình YAML
D. Quét toàn bộ bean bằng reflection sau mỗi request
Đáp án đúng: A

Câu 03. Với mô hình closed-world của Native Image, vấn đề nào cần xử lý cẩn thận?
A. Classpath tự mở rộng theo plugin mới khi ứng dụng chạy
B. Bean definitions tự cập nhật khi thư viện JAR được thêm
C. Model class được biên dịch lại sau khi ứng dụng deploy
D. Các kiểu được tải động cần có thông tin reachability
Đáp án đúng: D

Câu 04. Khác biệt cơ bản khi chạy ứng dụng native so với JAR Spring Boot là gì?
A. Chạy bytecode được đóng gói bằng lệnh `java -jar`
B. Thực thi binary mà không khởi động HotSpot JVM
C. Thực thi class Java qua JIT sau vài request đầu
D. Chạy JAR qua cùng JVM nhưng với một classloader mới
Đáp án đúng: B

Câu 05. Vì sao ứng dụng Native Image thường khởi động nhanh hơn bản JVM?
A. AOT chuẩn bị sẵn nhiều bước ngay trong lúc build
B. Web server tự bỏ bước đăng ký endpoint lúc chạy
C. Spring bỏ cơ chế quản lý vòng đời ApplicationContext
D. JVM được cấu hình heap lớn hơn khi nhận request đầu
Đáp án đúng: A

Câu 06. Muốn kiểm nhận định native tiết kiệm bộ nhớ, nên đo chỉ số nào?
A. So kích thước file source Java trước khi biên dịch
B. So số dependency khai báo trong `pom.xml` của dự án
C. So số dòng log tạo ra trong giai đoạn ứng dụng startup
D. Đo RSS với workload và cấu hình như nhau
Đáp án đúng: D

Câu 07. Một đánh đổi thường gặp khi build GraalVM Native Image là gì?
A. Build không cần kiểm tra phiên bản của các dependency
B. Build bỏ qua bước liên kết mã của các thư viện dự án
C. Build tự giảm kích thước dataset của ứng dụng đang dùng
D. Build tốn thêm thời gian và bộ nhớ cho phân tích mã
Đáp án đúng: D

Câu 08. Sau khi chuyển sang native, có thể kết luận throughput tốt hơn chỉ từ startup nhanh hơn không?
A. Có thể suy throughput từ kích thước file executable
B. Có thể suy throughput từ số resource hint đã khai báo
C. Benchmark riêng throughput dưới tải có tính đại diện
D. Có thể suy throughput từ thời gian JVM khởi tạo bean
Đáp án đúng: C

Câu 09. Với Maven và GraalVM Native Build Tools đã cấu hình, lệnh nào tạo native executable?
A. Chạy `mvn test` để tạo executable từ kết quả unit test
B. Chạy `mvn package -DskipTests` để ép đầu ra thành native
C. Chạy `mvn -Pnative native:compile` để biên dịch native
D. Chạy `mvn dependency:tree` để tạo binary cho hệ đích
Đáp án đúng: C

Câu 10. Với Gradle GraalVM Native Build Tools, task nào biên dịch ứng dụng native?
A. Dùng `nativeCompile` để tạo executable native
B. Dùng `processResources` để biên dịch executable native
C. Dùng `bootRun` để build executable native
D. Dùng `dependencies` để biên dịch executable native
Đáp án đúng: A

Câu 11. Khi dùng Cloud Native Buildpacks để đóng gói bản Spring Boot native, bước nào là trọng tâm?
A. Builder cần chèn bộ compiler vào runtime container khi chạy
B. Builder cần chuyển metadata AOT thành profile Spring
C. Builder cần bật JIT profiling trong JVM của runtime image
D. Builder cần được cấu hình thực hiện native-image build
Đáp án đúng: D

Câu 12. Một máy CI biên dịch Native Image cần điều kiện nào ngoài JDK chạy ứng dụng thông thường?
A. Toolchain Native Image và thư viện hệ thống tương thích
B. Một servlet container đã khởi chạy ở mỗi node CI
C. Một vector database phục vụ cho AOT bean generator
D. Một process Spring Boot chạy trước khi bắt đầu compile
Đáp án đúng: A

Câu 13. Vì sao không nên dùng trực tiếp cùng một binary native cho mọi nền tảng triển khai?
A. Binary chỉ nhận được request qua localhost khi chạy
B. Binary chứa tên active profile của máy developer
C. Binary phụ thuộc hệ điều hành và kiến trúc được biên dịch
D. Binary phụ thuộc phiên bản của từng file cấu hình YAML
Đáp án đúng: C

Câu 14. Nếu native build thất bại do thiếu RAM trên CI, cách xử lý nào hợp lý?
A. Giảm timeout HTTP của endpoint đang được benchmark
B. Cấp đủ RAM cho giai đoạn native compilation
C. Đổi giá trị `server.port` trong `application.yml`
D. Tăng heap của web server sau khi ứng dụng đã startup
Đáp án đúng: B

Câu 15. Khi một thư viện gọi method bằng reflection nhưng native runtime báo không tìm thấy, nên kiểm gì?
A. Thêm resource hint cho file chứa tên method đó
B. Đăng ký JDK proxy cho class chứa method được gọi
C. Thêm reflection hint cho member được gọi
D. Chỉ dùng constructor hint thay cho phương thức lỗi
Đáp án đúng: C

Câu 16. Ứng dụng tạo tên class từ cấu hình và dùng `Class.forName`; rủi ro chính khi native build là gì?
A. Native binary tự tải thêm bytecode từ JAR được gắn ngoài
B. Tên class tự chuyển thành tên bean để Spring tạo proxy
C. Kiểu nạp động có thể thiếu trong tập reachability lúc build
D. JVM classloader sẽ biên dịch class mới sau khi deploy
Đáp án đúng: C

Câu 17. Muốn cho phép gọi constructor qua reflection ở bản native, cần đăng ký gì?
A. Proxy hint cho chuỗi các interface được cài đặt
B. Serialization hint cho payload gửi qua socket
C. Resource hint cho file được tải qua classpath
D. Reflection hint cho constructor được truy cập động
Đáp án đúng: D

Câu 18. Trong Spring AOT, loại tích hợp nào khai báo các runtime hints tùy chỉnh?
A. Triển khai `ApplicationRunner` để sinh hints khi server ready
B. Triển khai `RuntimeHintsRegistrar` cho mã cần truy cập động
C. Triển khai `CommandLineRunner` để ghi hints sau deploy
D. Triển khai `BeanPostProcessor` để biên dịch lại executable
Đáp án đúng: B

Câu 19. Muốn đưa một `RuntimeHintsRegistrar` vào quá trình AOT của cấu hình Spring, annotation nào phù hợp?
A. Dùng `@ImportRuntimeHints` để đăng ký registrar
B. Dùng `@Profile` để đăng ký registrar
C. Dùng `@ImportResource` để đăng ký registrar
D. Dùng `@EnableScheduling` để đăng ký registrar
Đáp án đúng: A

Câu 20. Ứng dụng đọc template từ classpath bằng `getResourceAsStream`, nhưng native thiếu file; hướng sửa nào đúng?
A. Thay reflection constructor cho các lớp controller
B. Đổi `server.port` để classpath được quét lại khi chạy
C. Đăng ký JDK proxy cho các interface của template
D. Đăng ký resource pattern cho classpath template
Đáp án đúng: D

Câu 21. Khi ứng dụng dùng `ResourceBundle` cho bản dịch, dạng runtime metadata nào cần xem xét?
A. Đăng ký resource bundle phục vụ tra cứu thông điệp
B. Đăng ký proxy interface cho các file thông điệp
C. Đăng ký constructor của servlet filter ở build time
D. Đăng ký tên bean vào bảng routing của web server
Đáp án đúng: A

Câu 22. Thành phần `RuntimeHints` nào liên quan đến JDK dynamic proxy?
A. Nhóm reflection hints tự tạo proxy trong servlet container
B. Nhóm proxy hints khai báo các interface được proxy
C. Nhóm resource hints khai báo đường dẫn của proxy class
D. Nhóm serialization hints khai báo thứ tự HTTP filter
Đáp án đúng: B

Câu 23. Vì sao tập interface quan trọng khi một thư viện tạo JDK proxy trong native image?
A. Proxy động cần metadata cho tổ hợp interface được dùng
B. Proxy thay class concrete thành source Java tại runtime
C. Proxy buộc Spring tắt dependency injection trong native
D. Proxy tự tra cứu class mới từ internet lúc startup
Đáp án đúng: A

Câu 24. Một thư viện JSON truy cập các DTO bằng reflection ngoài đường AOT nhận biết; cần làm gì?
A. Đảm bảo các DTO và member có reflection hints phù hợp
B. Thêm JIT compiler vào container để parse JSON động
C. Chỉ đổi `@RestController` sang `@Controller` rồi build
D. Chỉ bật debug logging trong `application.properties`
Đáp án đúng: A

Câu 25. GraalVM tracing agent hữu ích trong công đoạn nào của native migration?
A. Chuyển file thực thi native thành source code Java
B. Thay Spring AOT sinh toàn bộ endpoint theo OpenAPI
C. Agent ghi lại thao tác động thực sự chạy để gợi ý metadata
D. Biên dịch binary native bên trong một request HTTP
Đáp án đúng: C

Câu 26. Vì sao kết quả ghi của tracing agent chưa bảo đảm đủ metadata?
A. Agent loại bỏ metadata của thư viện không dùng tới
B. Agent tự kích hoạt các profile chưa chạy trên CI
C. Agent đánh giá độ đúng nghiệp vụ thay cho test suite
D. Các nhánh chưa được chạy có thể chưa được quan sát
Đáp án đúng: D

Câu 27. Khi dependency đã cung cấp GraalVM reachability metadata, lợi ích nào thường có?
A. Thay build native bằng vòng lặp thực thi HotSpot JVM
B. Bỏ nhu cầu kiểm thử các API tích hợp của thư viện
C. Giảm cấu hình thủ công cho truy cập động của thư viện
D. Đưa credential production vào tệp metadata lúc build
Đáp án đúng: C

Câu 28. Một dependency dùng reflection chưa được hỗ trợ tốt trong native mode; cách tiếp cận nào hợp lý?
A. Thay tên package của dependency khi deploy
B. Kiểm metadata/hints và thử nghiệm luồng thực tế của nó
C. Tăng số thread để reflection hoạt động như JVM
D. Chuyển thời gian khởi động sang background worker
Đáp án đúng: B

Câu 29. Khi điều kiện tạo bean đã được quyết định ở pha AOT, thay property runtime có giới hạn gì?
A. Spring tạo lại toàn bộ binary khi property runtime đổi
B. Profile runtime sẽ biên dịch lại những class bị loại
C. Bean bị loại trong AOT có thể vắng khi chạy native
D. Bean bị loại khi build sẽ tự xuất hiện sau mỗi request
Đáp án đúng: C

Câu 30. Một class lưu thời gian hiện tại trong static field khi build-time initialization; rủi ro nào có thể xảy ra?
A. Giá trị tĩnh có thể bị chụp từ thời điểm tạo image
B. Giá trị tĩnh được tự tính lại cho mỗi lời gọi getter
C. Giá trị tĩnh chuyển thành biến môi trường khi deploy
D. Giá trị tĩnh bị xóa khỏi executable sau khi link
Đáp án đúng: A

Câu 31. Với class chứa state cần lấy theo môi trường lúc chạy, chiến lược khởi tạo nào phù hợp?
A. Chuyển state thành constant được nhúng ở compile-time
B. Chuyển class cần thiết sang runtime initialization
C. Chuyển class đó sang build-time initialization sớm
D. Khóa toàn bộ `ApplicationContext` vào lúc native build
Đáp án đúng: B

Câu 32. Ứng dụng native đọc `application.properties` bên ngoài executable lúc khởi động; nhận định nào phù hợp?
A. File ngoài làm runtime tự bật lại HotSpot classloader
B. File ngoài chỉ có tác dụng khi build bằng Gradle task
C. File ngoài cần được biên dịch vào executable mới đọc được
D. Config ngoài vẫn có thể được nạp theo cơ chế Spring Boot
Đáp án đúng: D

Câu 33. Với Gradle và GraalVM Native Build Tools, task nào được dùng để chạy test biên dịch native?
A. `testClasses` chạy test như native executable riêng
B. `processTestResources` tạo bản native cho test suite
C. `bootRun` chạy test qua binary native đã triển khai
D. `nativeTest` chạy bộ kiểm thử dưới dạng native executable
Đáp án đúng: D

Câu 34. Vì sao unit test thành công trên JVM chưa đủ để xác nhận bản native tương thích?
A. Native binary không hỗ trợ xác minh HTTP endpoint
B. JVM unit test làm thay đổi AOT metadata trong repository
C. Native có thể khác về reflection, resource và class init
D. JVM unit test thay đổi cấu hình mạng của container native
Đáp án đúng: C

Câu 35. Kịch bản smoke test nào nên thực thi trên chính binary native đã build?
A. Chỉ chạy formatter cho các class Java của dự án
B. Chạy native binary rồi kiểm endpoint nghiệp vụ
C. Chỉ đọc nội dung POM mà không chạy executable
D. Chỉ kiểm thời gian Gradle tải dependency từ mirror
Đáp án đúng: B

Câu 36. Khi đóng gói ứng dụng native vào container, vì sao runtime image có thể tối giản hơn ảnh JVM?
A. Binary native không cần thư viện hệ điều hành nào
B. Binary native không cần phân phối một HotSpot JVM đầy đủ
C. Binary native tự tạo container mà không cần image layer
D. Binary native không chịu ảnh hưởng khác biệt CPU/OS
Đáp án đúng: B

Câu 37. Với secret production, nguyên tắc nào phù hợp khi build executable native?
A. Chèn secret vào tên executable để dễ chọn deployment
B. Ghi secret vào static constant được khởi tạo lúc build
C. Cấp secret ở runtime thay vì nhúng vào build artifact
D. Đưa secret vào metadata reflection để tránh đọc từ env
Đáp án đúng: C

Câu 38. Muốn so hiệu năng JVM với native cho cùng service, phép đo nào có ý nghĩa?
A. So kích thước chuỗi phiên bản và số ký tự tên container
B. So startup, RSS, latency và throughput trên cùng workload
C. So số profile YAML mặc định và số dependency chưa dùng
D. So số lượng file Java và số package được Spring scan
Đáp án đúng: B

Câu 39. Native runtime báo không tìm thấy classpath template khi một endpoint được gọi; kiểm tra trước gì?
A. Resource hints và tài nguyên đã được nhúng vào image
B. Giá trị max heap của JVM chạy trong native process
C. Số lần refresh ApplicationContext sau khi nhận request
D. Thứ tự các thread gọi `CommandLineRunner`
Đáp án đúng: A

Câu 40. Trước khi triển khai bản native lên production, gate nào nên có ngoài thành công của native build?
A. Chỉ đo thời gian tải Gradle cache khi chạy CI
B. Kiểm tra chức năng, giới hạn tài nguyên và phương án rollback
C. Chỉ đối chiếu kích thước file binary với phiên bản cũ
D. Chỉ kiểm tra lệnh build thành công trên máy developer
Đáp án đúng: B
