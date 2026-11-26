1. Vì sao dự án Java nên commit Gradle Wrapper vào repository?
A. Dùng phiên bản Gradle đã chốt khi chạy `./gradlew`
B. Bỏ qua mọi dependency chưa có trong cache local
C. Tự chuyển đổi toàn bộ build script sang Kotlin DSL
D. Giữ riêng artifact sau khi build trong Wrapper JAR
Đáp án đúng: A

2. Trong Gradle Wrapper, `distributionUrl` xác định điều gì?
A. URL repository chứa dependency của ứng dụng
B. Địa chỉ kho artifact để plugin xuất bản JAR
C. Nguồn tải bản phân phối Gradle cần sử dụng
D. URL endpoint test của dịch vụ Java đang build
Đáp án đúng: C

3. Trong `settings.gradle.kts`, lệnh `include(":core")` thực hiện gì?
A. Đưa JAR `core` vào compile classpath trực tiếp
B. Thêm một task `core` vào mọi project trong build
C. Đưa project `core` vào một multi-project build
D. Yêu cầu Gradle tự phát hành artifact `core`
Đáp án đúng: C

4. Vai trò phổ biến của `build.gradle.kts` trong một project là gì?
A. Chọn mọi project con của toàn bộ build đa module
B. Khai báo plugin, dependency và task của project
C. Lưu file cấu hình JVM trước khi cài Gradle
D. Chứa kết quả biên dịch của task Java compile
Đáp án đúng: B

5. Đuôi file nào thường đại diện cho build script Gradle Kotlin DSL?
A. `build.gradle` sử dụng cú pháp Kotlin thuần
B. `build.xml` sử dụng cú pháp Kotlin theo XML
C. `build.gradle.kts` sử dụng cú pháp Kotlin
D. `pom.xml` sử dụng cú pháp Kotlin theo POM
Đáp án đúng: C

6. Khi áp plugin `java` của Gradle, điều gì được cung cấp?
A. Tự tạo source Java từ mọi dependency tải về
B. Buộc mọi task của dự án chạy theo thứ tự tên
C. Thêm task như `compileJava`, `test` và `jar`
D. Đưa artifact lên repository Maven ngay khi build
Đáp án đúng: C

7. Quan hệ `dependsOn` giữa hai Gradle task mang ý nghĩa gì?
A. Task được phụ thuộc chạy trước task yêu cầu nó
B. Task được phụ thuộc chỉ chạy sau khi task kia fail
C. Hai task bắt buộc cùng được publish thành một JAR
D. Task được phụ thuộc luôn chạy trong một JVM riêng
Đáp án đúng: A

8. So với `dependsOn`, `mustRunAfter` khác ở đặc điểm nào?
A. Luôn làm task khác trở thành dependency bắt buộc
B. Tự chạy các task khi kết thúc giai đoạn cấu hình
C. Chỉ hỗ trợ task được tạo từ plugin Java tiêu chuẩn
D. Chỉ quy định thứ tự nếu cả hai task được chạy
Đáp án đúng: D

9. Trong Gradle, cấu hình `onlyIf` của task có tác dụng gì?
A. Buộc task phải có ít nhất một dependency được tải
B. Bỏ qua thực thi task khi điều kiện đánh giá false
C. Chạy task sau mọi task khác bất kể task graph
D. Đánh dấu task luôn được tính là up-to-date
Đáp án đúng: B

10. Hai giai đoạn configuration và execution khác nhau thế nào?
A. Configuration dựng task graph; execution chạy task
B. Configuration chạy test; execution chỉ tải plugin
C. Configuration đóng JAR; execution công bố artifact
D. Configuration chỉ chạy khi dùng Kotlin DSL của Gradle
Đáp án đúng: A

11. Lệnh `./gradlew tasks` hữu ích khi cần biết thông tin gì?
A. Danh sách class cần đưa vào Java runtime image
B. Danh sách task Gradle có thể gọi trong project
C. Danh sách lỗi static analysis của mọi module
D. Danh sách version artifact vừa có trên Maven Central
Đáp án đúng: B

12. Lệnh `./gradlew dependencies` thường cung cấp gì?
A. Tất cả file nguồn thay đổi kể từ bản commit mới nhất
B. Toàn bộ nội dung log runtime của Java application
C. Sơ đồ quan hệ gọi hàm giữa các class Java trong JAR
D. Cây dependency theo từng cấu hình được Gradle liệt kê
Đáp án đúng: D

13. Khi Gradle chọn version thư viện không mong đợi, nên dùng công cụ nào?
A. `tasks` để kiểm tra những task có cùng tên thư viện
B. `properties` để kiểm tra class nào đã tải thư viện
C. `test` để in ra danh sách toàn bộ dependency jar
D. `dependencyInsight` để xem lý do chọn phiên bản
Đáp án đúng: D

14. Trong plugin `java-library`, khai báo `api` khác `implementation` thế nào?
A. `api` đưa dependency lên compile classpath của consumer
B. `implementation` luôn làm dependency xuất hiện tại mọi API
C. `api` chỉ được resolve khi chạy ứng dụng trong production
D. `implementation` cấm dependency xuất hiện tại runtime
Đáp án đúng: A

15. Khi hai nhánh Gradle yêu cầu version khác nhau, mặc định thường chọn gì?
A. Ưu tiên phiên bản được khai báo ở nhánh đầu tiên
B. Ưu tiên phiên bản cao hơn nếu không có ràng buộc khác
C. Ưu tiên phiên bản gần root project hơn trên cây phụ thuộc
D. Ưu tiên phiên bản từng được tải trong cache trước đó
Đáp án đúng: B

16. Khai báo `runtimeOnly` có ảnh hưởng gì đến classpath?
A. Có mặt ở compile nhưng bị loại khỏi runtime classpath
B. Có mặt ở runtime nhưng không nằm trên compile classpath
C. Chỉ có mặt khi ứng dụng được xuất bản lên repository
D. Chỉ có mặt ở Gradle buildscript chứ không ở ứng dụng
Đáp án đúng: B

17. Java Toolchains trong Gradle giúp quản lý điều gì?
A. Chọn plugin nào được tải từ kho Maven ngoài mạng
B. Chọn thời gian hết hạn của cache kết quả build
C. Chọn số bản phát hành artifact cần giữ trên server
D. Chọn JDK phù hợp cho tác vụ biên dịch và kiểm thử
Đáp án đúng: D

18. Khi nào Gradle có thể ghi nhận một task `UP-TO-DATE`?
A. Task đã chạy ít nhất một lần trong IDE của người dùng
B. Task từng thành công ở một repository không liên quan
C. Đầu vào và đầu ra đã khai báo không đổi phù hợp
D. Task nằm cuối đồ thị dependency được người dùng gọi
Đáp án đúng: C

19. Build cache của Gradle hữu ích trong trường hợp nào?
A. Tái dùng output mọi task bất kể nội dung input thay đổi
B. Lưu kết quả test làm mặc định cho mọi phiên bản dự án
C. Tái sử dụng output của task cacheable theo input tương ứng
D. Thay thế hoàn toàn source Java cần dùng khi compile
Đáp án đúng: C

20. `--configuration-cache` có mục tiêu hiệu năng nào?
A. Chạy toàn bộ task trong graph thành một luồng duy nhất
B. Tái dùng kết quả cấu hình khi điều kiện cache phù hợp
C. Bỏ qua mọi bước resolve dependency khi online
D. Tự nâng phiên bản JVM ở thời điểm bắt đầu build
Đáp án đúng: B

21. Chạy `./gradlew --offline build` yêu cầu điều kiện nào để thành công?
A. Mọi dependency phải vừa được tải mới từ Internet
B. Không project nào có thể khai báo dependency bắc cầu
C. Chỉ plugin Kotlin DSL mới được phép hoạt động offline
D. Các dependency cần thiết có sẵn trong cache cục bộ
Đáp án đúng: D

22. Dependency locking của Gradle hỗ trợ mục tiêu gì?
A. Loại hết mọi dependency bắc cầu khỏi runtime classpath
B. Ép tất cả library dùng version cao nhất có trên mạng
C. Bỏ qua version catalog của những project khác
D. Ghi lại phiên bản đã resolve để tái lập dependency
Đáp án đúng: D

23. Task `test` của plugin Java Gradle có mục đích chính gì?
A. Chạy test thuộc test source set của project Java
B. Đóng gói Java source thành một file JAR để publish
C. Tải và khóa tất cả dependency trên Maven Central
D. Sinh file `settings.gradle` cho dự án đa module
Đáp án đúng: A

24. Muốn xuất bản artifact Gradle theo định dạng Maven, nên cấu hình gì?
A. Plugin `maven-publish` cùng publication và repository
B. Plugin `java` với task `test` nhưng không có repository
C. Task `jar` rồi chỉ nén source mà không khai báo metadata
D. Task `clean` kết hợp `dependencies` để upload artifact
Đáp án đúng: A
