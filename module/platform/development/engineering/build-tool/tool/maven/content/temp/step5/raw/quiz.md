1. Trong Maven, vai trò chính của file `pom.xml` là gì?
A. Chỉ lưu log kết quả compile của JVM đang chạy
B. Chỉ chứa danh sách class đã biên dịch trong JAR
C. Mô tả dependency, plugin và cấu hình build
D. Chỉ quản lý credential để truy cập repository
Đáp án đúng: C

2. Bộ tọa độ nào thường nhận diện một artifact Maven cụ thể?
A. `groupId`, `scope` và tên file class của artifact
B. `artifactId`, `phase` và `goal` của plugin
C. `repository`, `packaging` và tên task mặc định
D. Tổ hợp `groupId`, `artifactId` và `version`
Đáp án đúng: D

3. Nếu POM không khai báo `<packaging>`, Maven dùng kiểu nào mặc định?
A. Kiểu `pom` dành cho mọi module con mặc định
B. Kiểu `jar` cho một dự án Java thông thường
C. Kiểu `war` dành cho ứng dụng Java bất kỳ
D. Kiểu `zip` để gộp cả source và dependency
Đáp án đúng: B

4. Với bố cục chuẩn Maven, Java source và test source nằm ở đâu?
A. `source/main` và `source/test` tương ứng
B. `classes/main` và `classes/test` tương ứng
C. `main/src` và `test/src` theo thứ tự
D. `src/main/java` và `src/test/java`
Đáp án đúng: D

5. Chạy `mvn package` thường kích hoạt những bước nào?
A. Chạy các phase tới và bao gồm `package`
B. Chỉ phase `package`, không chạy phase trước
C. Chỉ phase `deploy` để đẩy artifact lên kho
D. Chỉ phase `clean` để xóa toàn bộ output
Đáp án đúng: A

6. Chạy `mvn test` trong lifecycle mặc định có tác dụng gì?
A. Chỉ tạo artifact JAR và chuyển vào local repository
B. Biên dịch mã cần thiết và chạy test, chưa đóng gói
C. Đẩy artifact sau khi kiểm thử lên remote repository
D. Xóa thư mục target rồi chạy toàn bộ phase deploy
Đáp án đúng: B

7. Lệnh `mvn clean package` khác `mvn package` ở điểm nào?
A. Tự động tải snapshot mới nhất từ mọi repository
B. Bỏ qua tất cả bước kiểm thử trong lifecycle
C. Tự cài Java compiler vào máy trước khi build
D. Chạy clean trước khi build tới phase package
Đáp án đúng: D

8. Trong Maven, plugin nào thường cấu hình mức Java release khi biên dịch?
A. `maven-surefire-plugin` với tham số `release`
B. `maven-deploy-plugin` với tham số `release`
C. `maven-site-plugin` với tham số `release`
D. `maven-compiler-plugin` với tham số `release`
Đáp án đúng: D

9. Plugin nào thường chạy unit test trong Maven lifecycle?
A. `maven-failsafe-plugin` chỉ đóng gói JAR test
B. `maven-surefire-plugin` thực thi unit test
C. `maven-jar-plugin` thực thi unit test
D. `maven-clean-plugin` chỉ chạy unit test
Đáp án đúng: B

10. Với integration test, Maven Failsafe thường dùng cặp goal nào?
A. `compile` và `package` để chạy và kiểm tra
B. `clean` và `install` để chạy và kiểm tra
C. `site` và `deploy` để chạy và kiểm tra
D. Dùng goal `integration-test` và `verify`
Đáp án đúng: D

11. Khi kiểm tra artifact trước khi cài vào kho local, `mvn verify` làm gì?
A. Chỉ gọi Maven Central để tải các plugin chưa có
B. Chỉ copy artifact vào thư mục cache người dùng
C. Chạy các phase tới `verify` trong lifecycle
D. Chỉ xuất bản artifact lên kho phân phối từ xa
Đáp án đúng: C

12. `<execution>` trong cấu hình Maven plugin hỗ trợ điều gì?
A. Gắn plugin goal vào phase để thực thi
B. Gắn repository với một groupId và một artifactId
C. Gắn module con với đường dẫn source trong Java
D. Gắn version phụ thuộc với file manifest của JAR
Đáp án đúng: A

13. Dependency có Maven scope `compile` thường hiện diện ở đâu?
A. Chỉ ở lúc chạy test, không ở runtime production
B. Classpath compile, test và runtime của dự án
C. Chỉ ở lúc xuất bản artifact lên Maven Central
D. Chỉ ở JVM chạy Maven, không ở ứng dụng biên dịch
Đáp án đúng: B

14. Scope `provided` phù hợp với thư viện được môi trường chạy cung cấp vì sao?
A. Chỉ có trong runtime, không có trên compile classpath
B. Chỉ tải khi Maven build ở chế độ `--offline`
C. Có lúc compile/test nhưng không vào runtime mặc định
D. Luôn được đóng gói vào JAR của chính module
Đáp án đúng: C

15. Dependency với scope `test` trong Maven có ý nghĩa gì?
A. Chỉ dùng cho biên dịch và chạy mã kiểm thử
B. Chỉ dùng để phát hành artifact lên remote repository
C. Chỉ dùng trong mã production khi JVM khởi động
D. Chỉ dùng để kích hoạt mọi Maven plugin của dự án
Đáp án đúng: A

16. Khối `<dependencyManagement>` trong Maven thường làm gì?
A. Tự thêm mọi dependency được khai báo vào classpath
B. Chỉ chứa danh sách plugin sẽ chạy ở phase package
C. Ép mọi dependency thành scope runtime lúc build
D. Quản lý version mà không tự thêm dependency
Đáp án đúng: D

17. Để import một BOM Maven vào dependency management, dùng gì?
A. Dependency `type=pom`, `scope=import` trong management
B. Dependency `type=jar`, `scope=compile` trong management
C. Plugin `type=pom`, `scope=test` trong lifecycle
D. Repository `type=war`, `scope=provided` trong settings
Đáp án đúng: A

18. Khi hai nhánh Maven kéo hai version cùng artifact, mặc định điều gì quyết định?
A. Version có số lớn nhất luôn được ưu tiên chọn
B. Version từ đường phụ thuộc gần root hơn được chọn
C. Version xuất hiện sau cùng trong metadata được chọn
D. Version tải về cache trước luôn được ưu tiên chọn
Đáp án đúng: B

19. Lệnh nào giúp xem cây dependency của dự án Maven?
A. Dùng `mvn dependency:tree` để xem nhánh phụ thuộc
B. `mvn help:effective-pom` hiển thị log runtime
C. `mvn compiler:compile` hiển thị các repository
D. `mvn surefire:test` hiển thị cây dependency
Đáp án đúng: A

20. Maven mặc định cache dependency tải về tại đâu?
A. Thư mục `target/classes` của từng module
B. Thư mục `src/test/resources` của project
C. Thư mục `~/.m2/repository` theo mặc định
D. Thư mục source Java ở `src/main/java`
Đáp án đúng: C

21. File `settings.xml` của Maven phù hợp lưu loại cấu hình nào?
A. Mọi khai báo class Java sẽ được đóng thành JAR
B. Thiết lập mirror, server và credential
C. Mọi phase của lifecycle thay thế cho POM gốc
D. Mọi test case và assert của thư viện JUnit
Đáp án đúng: B

22. Trong Maven đa module, POM aggregator thường khai báo gì?
A. `packaging=pom` và danh sách module con
B. `packaging=jar` và danh sách class đã biên dịch
C. `packaging=war` và danh sách toàn bộ unit test
D. `packaging=zip` và tên máy chủ artifact
Đáp án đúng: A

23. Lệnh `mvn -pl :service -am package` thường có tác dụng gì?
A. Chỉ build dependency bên ngoài đã tải từ Maven Central
B. Bỏ toàn bộ module con khỏi reactor rồi đóng JAR
C. Build module `service` với các dependency reactor cần thiết
D. Đẩy mọi module đã build lên remote repository
Đáp án đúng: C

24. So với `mvn install`, `mvn deploy` khác ở điểm nào?
A. `deploy` chỉ tạo file trong `target/classes` của project
B. `install` luôn xuất artifact ra repository Maven Central
C. `deploy` đưa artifact lên remote repo thay vì chỉ local
D. `install` chỉ biên dịch source mà không chạy test
Đáp án đúng: C
