Câu 1. Trong Maven, kế thừa `spring-boot-starter-parent` hỗ trợ điều gì khi build?
A. Tự dùng bản mới nhất của mọi plugin và dependency khi build.
B. Chỉ thêm repository nhưng không quản lý phiên bản dependency.
C. Chỉ quản lý classpath runtime mà không cấu hình plugin.
D. Quản lý dependency và cấu hình plugin mặc định của dự án.
Đáp án đúng: D

Câu 2. Dùng `spring-boot-dependencies` làm BOM import thay vì parent Maven có điểm gì?
A. Tự đổi packaging của mọi module Maven thành `war`.
B. Tự gắn goal `repackage` vào lifecycle của mọi module.
C. BOM quản lý version dependency, không kế thừa plugin config.
D. Tự thêm plugin compiler và cấu hình test runner cho dự án.
Đáp án đúng: C

Câu 3. Một dependency được BOM quản lý phiên bản, nhưng khai báo trực tiếp version khác. Maven xử lý ra sao?
A. BOM luôn ghi đè version được đặt trong dependency.
B. Spring Boot plugin luôn chọn version mới nhất từ kho.
C. Ưu tiên version ghi trực tiếp tại dependency đó.
D. Version được quyết định theo tên artifact đã tải.
Đáp án đúng: C

Câu 4. Goal nào của `spring-boot-maven-plugin` đóng gói lại JAR/WAR để chạy được?
A. Dùng goal `clean` để sinh manifest và nested libraries.
B. Dùng goal `build-image` để tạo lại executable JAR.
C. Dùng goal `test` để nhúng thư viện runtime vào JAR.
D. Dùng goal `repackage` để tạo archive có Boot Loader.
Đáp án đúng: D

Câu 5. JAR chỉ chứa class ứng dụng bị lỗi thiếu thư viện khi `java -jar`. Cách khắc phục nào đúng?
A. Dùng `repackage` để đưa dependency vào executable JAR.
B. Chỉ đổi `Main-Class` nhưng giữ nguyên cấu trúc JAR.
C. Chỉ chạy test một lần ở máy trước khi triển khai.
D. Chỉ đổi phần mở rộng tệp JAR thành `boot.jar`.
Đáp án đúng: A

Câu 6. Lệnh Maven `spring-boot:build-image` nhằm tạo sản phẩm nào?
A. Tạo WAR cho máy chủ Servlet bên ngoài ứng dụng.
B. Tạo OCI image từ Dockerfile và bỏ qua Cloud Native Buildpacks.
C. Tạo Dockerfile nhiều stage mà không build image.
D. Tạo OCI image từ app bằng Cloud Native Buildpacks.
Đáp án đúng: D

Câu 7. Với Gradle Java plugin và Spring Boot plugin, task `bootJar` dùng để làm gì?
A. Khởi chạy ứng dụng trực tiếp mà không tạo artifact.
B. Đóng gói JAR thư viện mỏng không có Boot Loader.
C. Đóng gói JAR chạy được và thư viện runtime đi kèm.
D. Tạo Gradle dependency lockfile cho mọi dependency.
Đáp án đúng: C

Câu 8. So với task `jar` thông thường, `bootJar` khác biệt nổi bật nào?
A. Tạo image bằng Dockerfile thay vì đóng gói các class.
B. Tạo JAR thực thi có cấu trúc của Spring Boot.
C. Chỉ đóng gói source Java để dùng trong IDE của dự án.
D. Chỉ lưu các Maven POM rồi tải runtime khi khởi chạy.
Đáp án đúng: B

Câu 9. Trong executable Spring Boot JAR, thư mục `BOOT-INF/classes` thường chứa gì?
A. Class và resource đã biên dịch của ứng dụng.
B. Các tệp chỉ mục layer cho OCI image container.
C. Các JAR dependency đóng gói để nạp lúc chạy.
D. Các class launcher của Spring Boot Loader.
Đáp án đúng: A

Câu 10. Trong executable Spring Boot JAR, `BOOT-INF/lib` thường chứa gì?
A. Các JAR phụ thuộc được đặt lồng trong archive.
B. Những class chính đã được biên dịch từ source.
C. Các file Dockerfile dùng xây dựng container.
D. Các tệp khai báo layer để tối ưu Docker cache.
Đáp án đúng: A

Câu 11. Spring Boot Loader có vai trò gì khi chạy executable JAR?
A. Đẩy các dependency đang dùng lên Maven Central.
B. Tạo classpath bằng tùy chọn JVM `-cp` ở bên ngoài.
C. Biên dịch lại source Java khi JVM bắt đầu chạy.
D. Nạp class từ nested JAR trong archive của Boot.
Đáp án đúng: D

Câu 12. Trong manifest của executable Boot JAR, `Start-Class` thường chỉ định gì?
A. Class xác định cấu hình SSL của máy chủ Servlet.
B. `Start-Class` chỉ main class của ứng dụng.
C. Class dùng tạo image registry từ Buildpacks.
D. Class launcher `JarLauncher` của Spring Boot Loader.
Đáp án đúng: B

Câu 13. Với ứng dụng đóng gói WAR triển khai external Servlet container, cần chuẩn bị gì?
A. Loại bỏ hoàn toàn Spring Boot auto-configuration.
B. Chuyển mọi dependency sang scope `test` trong Maven.
C. Chuyển main class thành `JarLauncher` và đóng gói theo WAR.
D. Kế thừa `SpringBootServletInitializer` để boot ứng dụng.
Đáp án đúng: D

Câu 14. Với WAR chạy trên external servlet container, embedded server dependency thường đặt scope nào?
A. Đặt ở `annotationProcessor` để đóng gói đầy đủ.
B. Đặt ở `testImplementation` để server nạp khi deploy.
C. Đặt ở `provided` hoặc `providedRuntime` phù hợp.
D. Đặt ở `compileOnly` rồi bỏ khỏi mọi cấu hình WAR.
Đáp án đúng: C

Câu 15. Nếu triển khai với `java -jar` trên máy có JVM, packaging nào thường thuận tiện?
A. Source JAR chỉ chứa code nguồn và tài liệu API.
B. Plain JAR không có dependency runtime cần thiết.
C. WAR bắt buộc chạy bằng container Servlet bên ngoài.
D. Chọn executable JAR kèm embedded servlet server.
Đáp án đúng: D

Câu 16. Maven Wrapper (`mvnw`) giúp pipeline CI đạt mục tiêu nào?
A. Đưa bản đã build lên Maven Central sau mỗi lần test.
B. `mvnw` dùng bản Maven được cấu hình trong wrapper.
C. Khóa toàn bộ phiên bản dependency trong `pom.xml`.
D. Chọn phiên bản Java Runtime theo tên Docker image.
Đáp án đúng: B

Câu 17. Gradle Wrapper (`gradlew`) có ích gì cho tính nhất quán bản dựng?
A. Tự thay mọi dependency version bằng bản mới nhất.
B. Dùng bản phân phối Gradle được cấu hình trong wrapper.
C. Tự đăng ký tất cả task của plugin Spring Boot.
D. Tự đảm bảo mọi output archive trùng bit bất chấp môi trường.
Đáp án đúng: B

Câu 18. Để tăng khả năng reproducible build, cách làm nào phù hợp?
A. Cố định tool, dependency và timestamp của archive.
B. Đổi cấu hình Java compiler ngẫu nhiên giữa các máy.
C. Gắn timestamp hiện tại vào mọi file trong archive.
D. Để phiên bản dependency động và luôn tải bản mới nhất.
Đáp án đúng: A

Câu 19. Gradle dependency locking chủ yếu giải quyết vấn đề nào?
A. Ghi mọi password truy cập registry vào file lock.
B. Thay hoàn toàn dependency verification và scan lỗ hổng.
C. Tự tạo container image mà không cần task build.
D. Khóa version đã resolve để build dùng nhất quán.
Đáp án đúng: D

Câu 20. Dùng Spring Boot BOM giúp nâng cấp thư viện theo cách nào?
A. Tự tạo lockfile và kiểm tra chữ ký từng JAR khi build.
B. Thay mọi dependency third-party bằng starter của Spring.
C. Tự áp đặt phiên bản Java và hệ điều hành trong image.
D. Quản lý các phiên bản dependency theo một BOM.
Đáp án đúng: D

Câu 21. Trong Docker multi-stage build, vì sao nên tách build stage và runtime stage?
A. Để image chạy chỉ giữ artifact cùng runtime cần thiết.
B. Để source và build cache luôn được giữ trong final image.
C. Để tránh phải compile ứng dụng trước khi container chạy.
D. Để mọi dependency được tải mới khi container khởi động.
Đáp án đúng: A

Câu 22. Trong Dockerfile nhiều stage, `COPY --from=build` thường dùng làm gì?
A. Sao chép nội dung image runtime ngược vào Git repository.
B. Sao chép artifact đã build sang stage đóng gói runtime.
C. Sao chép trạng thái container đang chạy sang base image.
D. Sao chép mọi secret của CI vào image để khởi động.
Đáp án đúng: B

Câu 23. Trong Dockerfile, dùng dạng exec `ENTRYPOINT ["java", "-jar", "app.jar"]` có lợi điểm nào?
A. Để image luôn được ký số ngay lúc container khởi động.
B. Để JVM bỏ qua mọi dependency đã đóng trong executable JAR.
C. JVM nhận trực tiếp tín hiệu dừng từ container runtime.
D. Để Docker tự sửa lỗi JVM mà không cần thay mã ứng dụng.
Đáp án đúng: C

Câu 24. Cloud Native Buildpacks trong Spring Boot `build-image` thường làm gì?
A. Yêu cầu dự án phải có Dockerfile do nhóm tự viết.
B. Dò ứng dụng và dựng image qua Buildpacks lifecycle.
C. Chỉ tạo file TAR chứa source nhưng không thể chạy.
D. Chỉ tải base image và không đóng gói ứng dụng.
Đáp án đúng: B

Câu 25. Ưu điểm của Buildpacks so với Dockerfile tự viết trong nhiều dự án là gì?
A. Giảm thao tác tự quản lý các bước đóng gói runtime.
B. Loại bỏ nhu cầu xem xét bảo mật của base image.
C. Tự triển khai image lên Kubernetes sau mọi lần build.
D. Đảm bảo container không cần bất kỳ JVM runtime nào.
Đáp án đúng: A

Câu 26. Spring Boot layered JAR hữu ích cho container image theo cách nào?
A. Chuyển tất cả bean thành một library JAR duy nhất.
B. Tách dependency và class để cache layer tốt hơn.
C. Bắt các HTTP request chạy ở lớp container riêng.
D. Bỏ requirement dùng classpath của Boot Loader.
Đáp án đúng: B

Câu 27. Khi code ứng dụng đổi nhưng dependency vẫn giữ nguyên, build theo layer giúp gì?
A. Bỏ qua compile ứng dụng và dùng bytecode bản cũ.
B. Thay đổi checksum của mọi thư viện từ Maven Central.
C. Giảm tạo lại layer dependency không bị ảnh hưởng.
D. Đặt tất cả lớp Boot Loader vào một layer mới.
Đáp án đúng: C

Câu 28. Vì sao container chạy ứng dụng nên tránh tài khoản root khi có thể?
A. Giảm quyền của tiến trình nếu ứng dụng bị khai thác.
B. Giảm số lượng dependency được đóng trong executable JAR.
C. Cho phép image không cần xác minh package đã tải.
D. Chỉ bật TLS để tiến trình có thể chạy với đặc quyền root.
Đáp án đúng: A

Câu 29. Để xử lý mật khẩu registry/database khi build image, nên làm gì?
A. Chèn secret vào `ARG` rồi ghi vào metadata của image.
B. Lưu secret vào `ENV` của final image để dùng khi chạy.
C. Không ghi secret vào layer; cấp động khi cần dùng.
D. Đóng gói secret trong `BOOT-INF/classes` cho tiện tải.
Đáp án đúng: C

Câu 30. SBOM có vai trò chính nào trong bảo vệ chuỗi cung ứng phần mềm?
A. Ghi file image thành định dạng có thể chạy không cần JVM.
B. Thay bản scan image bằng kết quả kiểm tra unit test.
C. Liệt kê thành phần và phiên bản phụ thuộc của bản phát hành.
D. Đảm bảo runtime container không thể có bất kỳ lỗ hổng.
Đáp án đúng: C

Câu 31. Khi phát hành container image qua CI, cách nào giúp kiểm tra tính toàn vẹn?
A. Ký và xác minh digest image kèm nguồn gốc build.
B. Cho phép sửa artifact sau khi ký mà không cần ký lại.
C. Tin vào tag `latest` vì nó được registry giữ bất biến.
D. Bỏ quét lỗ hổng nếu Docker build kết thúc thành công.
Đáp án đúng: A

Câu 32. Để tránh CI phát hành artifact khác bản vừa kiểm thử, nên làm gì?
A. Chỉ đối chiếu git commit mà không so digest artifact.
B. Phát hành đúng artifact đã qua test theo digest.
C. Build lại source với tag khác sau khi test hoàn tất.
D. Dùng tag image mới rồi bỏ bước xác minh digest.
Đáp án đúng: B
