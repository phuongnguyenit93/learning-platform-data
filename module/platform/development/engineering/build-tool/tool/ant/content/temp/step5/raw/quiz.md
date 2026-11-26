1. Trong Apache Ant, phần tử gốc của `build.xml` thường là gì?
A. `target` chứa mọi task mà không cần project
B. `fileset` chứa toàn bộ logic chạy build XML
C. `project` chứa tên, mặc định và các target
D. `path` chứa mọi lệnh và thuộc tính của Ant
Đáp án đúng: C

2. Thuộc tính `default` của `<project>` quy định điều gì?
A. Target bắt buộc chạy trước mọi target được yêu cầu
B. Target chỉ dùng khi chạy Ant qua một IDE cụ thể
C. Chạy target mặc định khi lệnh không chỉ rõ target
D. Target luôn chạy ngay sau bước biên dịch Java
Đáp án đúng: C

3. Khai báo `<target name="dist" depends="test">` có tác dụng gì?
A. Bảo đảm target `test` được chạy trước `dist`
B. Cho phép `test` và `dist` chạy song song mặc định
C. Bỏ qua `dist` nếu `test` chưa có mô tả `description`
D. Chuyển giá trị output của `test` thành thuộc tính `dist`
Đáp án đúng: A

4. Apache Ant có vòng đời chuẩn cố định như Maven không?
A. Không; thứ tự build được mô hình hóa bằng target
B. Có; tất cả project tự chạy chuỗi phase giống nhau
C. Có; Ant chỉ hỗ trợ các phase compile và package
D. Không; Ant không hỗ trợ quan hệ thứ tự giữa target
Đáp án đúng: A

5. Vì sao nên tách target `clean`, `compile`, `test`, `dist`?
A. Bắt buộc mỗi target được chạy trong một JVM khác
B. Giúp Ant tự động tải tất cả dependency từ Maven
C. Tách bước để dễ gọi riêng và tái sử dụng
D. Loại bỏ nhu cầu khai báo đường dẫn output build
Đáp án đúng: C

6. Với lệnh `ant -Denv=staging dist`, phần `-D` để làm gì?
A. Đặt property `env` từ dòng lệnh khi gọi Ant
B. Chọn file build tên `env` từ thư mục hiện hành
C. Bật tự động tải thư viện từ Ivy repository
D. Buộc Ant chạy target `env` trước target `dist`
Đáp án đúng: A

7. Đặc tính nào đúng với property thông thường của Ant?
A. Mọi target luôn có thể gán lại cùng tên property
B. Property chỉ tồn tại trong phạm vi một task cụ thể
C. Một khi đã đặt, giá trị không bị ghi đè tùy ý
D. Property chỉ hỗ trợ kiểu số nguyên và boolean
Đáp án đúng: C

8. Lệnh Ant nào chọn một file XML khác tên mặc định `build.xml`?
A. `ant -D ci-build.xml test` để chỉ định file
B. `ant -p ci-build.xml test` để chỉ định file
C. `ant -v ci-build.xml test` để chỉ định file
D. Dùng `ant -f ci-build.xml test` để chọn file
Đáp án đúng: D

9. `<mkdir dir="build/classes"/>` trong Ant làm gì?
A. Đóng gói thư mục class thành một file JAR mới
B. Xóa các class cũ để bảo đảm build sạch hoàn toàn
C. Tự động tải các thư viện Java vào thư mục class
D. Tạo thư mục class trước khi bước compile chạy
Đáp án đúng: D

10. Để biên dịch Java từ `src` sang `build/classes`, task nào phù hợp?
A. `java` với `srcdir` và `destdir` tương ứng
B. `javac` với `srcdir`, `destdir` đã khai báo
C. `jar` với `srcdir` và `destdir` tương ứng
D. `copy` với `srcdir` và `destdir` tương ứng
Đáp án đúng: B

11. `classpathref` của task `<javac>` thường tham chiếu tới gì?
A. Một `<target>` đã hoàn thành và có thuộc tính `name`
B. Một `<project>` khác đã có thuộc tính `default`
C. Một `<fileset>` bắt buộc chỉ chứa các file source
D. Một `<path>` đã được khai báo có thuộc tính `id`
Đáp án đúng: D

12. Trong Ant, `<pathelement location="lib/a.jar"/>` nằm trong `<path>` để làm gì?
A. Tự mở file JAR rồi đưa mọi class vào source tree
B. Xóa entry JAR đó khỏi mọi dependency của project
C. Thêm `lib/a.jar` vào đường dẫn classpath đã tạo
D. Đặt điều kiện chỉ chạy task khi JAR đã hết hạn
Đáp án đúng: C

13. Khi cần chọn tập JAR trong thư mục `lib` để làm classpath, nên dùng gì?
A. `property` với `dir="lib"` và mẫu chọn `**/*.jar`
B. `fileset` với `dir="lib"` và mẫu chọn `**/*.jar`
C. `target` với `dir="lib"` và mẫu chọn `**/*.jar`
D. `macrodef` với `dir="lib"` và mẫu chọn `**/*.jar`
Đáp án đúng: B

14. Với FileSet của Ant, `includes="**/*.java"` mô tả tập nào?
A. Các file `.java` ở thư mục gốc và thư mục con
B. Chỉ file `.java` nằm ngay thư mục gốc được khai báo
C. Chỉ các file `.class` trong thư mục đích build
D. Các thư mục có tên `.java` nhưng không gồm file
Đáp án đúng: A

15. Để loại `**/generated/**` khỏi một FileSet, nên sử dụng gì?
A. Cấu hình `depends` hoặc một thẻ `<depend>`
B. Cấu hình `classpath` hoặc một thẻ `<path>`
C. Cấu hình `default` hoặc một thẻ `<project>`
D. Dùng `excludes` hoặc thẻ `<exclude>` của FileSet
Đáp án đúng: D

16. Task nào đóng gói class đã biên dịch thành file JAR?
A. `<java destfile="dist/app.jar" basedir="build/classes"/>`
B. `<copy destfile="dist/app.jar" basedir="build/classes"/>`
C. `<jar destfile="dist/app.jar" basedir="build/classes"/>`
D. `<javac destfile="dist/app.jar" basedir="build/classes"/>`
Đáp án đúng: C

17. Khi muốn chép tài nguyên từ `resources` vào `build/classes`, dùng task nào?
A. `delete` cùng `todir` và một `fileset` nguồn phù hợp
B. `copy` cùng `todir` và một `fileset` nguồn phù hợp
C. `mkdir` cùng `todir` và một `fileset` nguồn phù hợp
D. `jar` cùng `todir` và một `fileset` nguồn phù hợp
Đáp án đúng: B

18. Trong target `clean`, task nào phù hợp để xóa thư mục `build`?
A. `<delete dir="build"/>` để xóa thư mục cũ
B. `<copy dir="build"/>` để bỏ nội dung build cũ
C. `<javac dir="build"/>` để bỏ nội dung build cũ
D. `<touch dir="build"/>` để bỏ nội dung build cũ
Đáp án đúng: A

19. Mục đích của `<macrodef>` trong Ant là gì?
A. Khai báo kho Ivy để mọi target tự tải dependency
B. Định nghĩa macro task tái dùng được với tham số
C. Phát hiện mã Java vi phạm quy tắc kiến trúc
D. Thay đổi phiên bản Ant đang dùng khi chạy CI
Đáp án đúng: B

20. Trong Apache Ivy, `ivy.xml` chủ yếu khai báo nội dung nào?
A. Mọi target Ant và thứ tự gọi target theo mặc định
B. Cú pháp Java cần biên dịch thành bytecode JAR
C. Các ngưỡng kiểm thử hiệu năng của hệ thống
D. Khai báo module và các dependency cần phân giải
Đáp án đúng: D

21. Sau khi tích hợp Ivy, `<ivy:resolve>` phục vụ bước nào?
A. Chép mọi file `.java` vào thư mục output của Ant
B. Phân giải dependency và lưu vào Ivy cache
C. Đóng gói ứng dụng thành JAR theo manifest
D. Thực thi tất cả unit test trước bước package
Đáp án đúng: B

22. Sự khác nhau giữa Ivy `resolve` và `retrieve` trong Ant là gì?
A. Resolve phân giải; retrieve chép artifact vào thư mục
B. Resolve luôn chạy test; retrieve luôn tạo báo cáo test
C. Resolve chỉ nén JAR; retrieve chỉ giải nén file JAR
D. Resolve khởi động JVM; retrieve chỉ thiết lập property
Đáp án đúng: A

23. Nếu dùng task `<junit>` trong Ant, cần lưu ý điều gì?
A. Ant tự cung cấp mọi bản JUnit mà không cần thư viện
B. Cần thư viện JUnit và classpath tương ứng với task
C. JUnit chỉ chạy được sau khi artifact đã được publish
D. JUnit chỉ nhận test từ thư mục chứa mã production
Đáp án đúng: B

24. Để quy trình Ant đáng tin cậy trong CI, lựa chọn nào phù hợp?
A. Dựa vào thư viện đang có ngẫu nhiên trên máy phát triển
B. Luôn bỏ qua lỗi compile để tiếp tục tạo file phát hành
C. Chỉ chạy target `clean` rồi coi pipeline đã được test
D. Chốt JDK, dependency và cấu hình build fail khi test lỗi
Đáp án đúng: D
