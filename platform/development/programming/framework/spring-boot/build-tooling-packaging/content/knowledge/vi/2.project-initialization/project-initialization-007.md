# Chạy bản dựng Spring Boot đầu tiên từ dòng lệnh trên Windows và Linux

## 1. Mục tiêu và kết quả cần đạt

Sau bài học, bạn có thể mở terminal tại thư mục gốc của một dự án Spring Boot mới khởi tạo, kiểm tra JDK, chạy bản dựng bằng Gradle Wrapper hoặc Maven Wrapper trên Windows và Linux, đọc kết quả thành công/thất bại và tìm được tệp đóng gói. Bạn cũng biết cách chạy thử ứng dụng sau khi build nếu dự án được cấu hình tạo JAR thực thi.

**Bản dựng (build)** là quá trình dùng cấu hình dự án để lấy dependency, biên dịch mã, xử lý resource, chạy những bước kiểm tra được cấu hình và tạo artifact. **Chạy ứng dụng (run)** là bước riêng: một lệnh build thành công chưa chứng minh ứng dụng khởi động được với môi trường hiện tại.

Bài này giả định bạn đã tạo hoặc tải một dự án Java Spring Boot (chẳng hạn từ Spring Initializr) có mã nguồn, tập tin cấu hình build và các Wrapper tương ứng. Không cần mở IDE để thực hiện.

## 2. Nhận diện dự án và chuẩn bị môi trường

Mở thư mục gốc dự án, nơi có file cấu hình build. Không chạy lệnh ở thư mục chứa riêng `src` hay thư mục tùy ý.

| Dấu hiệu trong thư mục gốc | Công cụ build | Wrapper trên Windows | Wrapper trên Linux |
| --- | --- | --- | --- |
| `build.gradle` hoặc `build.gradle.kts`, `settings.gradle[.kts]`, `gradlew`, `gradlew.bat` | Gradle | `gradlew.bat` | `./gradlew` |
| `pom.xml`, `mvnw`, `mvnw.cmd`, `.mvn/wrapper/` | Maven | `mvnw.cmd` | `./mvnw` |

Một dự án có thể chọn một trong hai công cụ. **Chỉ chạy bộ lệnh tương ứng với file build của dự án**; không dùng lệnh Maven trên dự án chỉ có Gradle hoặc ngược lại.

Điều kiện tối thiểu:

1. Cài **JDK**, không chỉ JRE. Với Spring Boot 3.x, Java 17 là mức tối thiểu; hãy kiểm tra phiên bản Java/toolchain mà dự án thực tế yêu cầu. Một dự án mới hơn hoặc tổ chức cụ thể có thể quy định JDK khác, ví dụ 21.
2. Terminal truy cập được `java` và `javac`. Thiết lập `JAVA_HOME` và `PATH` tới JDK đang dùng nếu chúng chưa đúng.
3. Được truy cập Internet hoặc kho cache/mirror của tổ chức để Wrapper tải Gradle/Maven và dependency lần đầu.
4. Thư mục dự án có script Wrapper và file cấu hình Wrapper tương ứng. Wrapper giúp dùng đúng phiên bản build tool mà dự án khai báo, không đòi hỏi cài Gradle/Maven toàn máy.

Kiểm tra từ bất cứ terminal nào:

~~~text
java -version
javac -version
~~~

Kết quả phải cho biết phiên bản Java/Javac khả dụng, cùng phiên bản JDK mong muốn. **Đừng sao chép số phiên bản từ ví dụ:** phiên bản đúng do cấu hình của dự án quyết định.

Nếu cần xem biến môi trường:

~~~powershell
# Windows PowerShell
$Env:JAVA_HOME
Get-Command java
Get-Command javac
~~~

~~~bash
# Linux (bash)
printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
~~~

`JAVA_HOME` thường trỏ tới thư mục gốc JDK (không phải thư mục `bin`). Sau khi thay biến môi trường, mở terminal mới và kiểm tra lại. Nếu dự án dùng Gradle Java toolchain, JDK dùng để chạy Gradle và JDK dùng biên dịch có thể khác nhau theo cấu hình; hãy đọc thông báo lỗi cụ thể.

## 3. Dùng Wrapper thay vì phụ thuộc build tool cài sẵn

Wrapper là script khởi chạy phiên bản Gradle/Maven được cấu hình trong dự án:

- **Gradle:** `gradlew`, `gradlew.bat` và `gradle/wrapper/gradle-wrapper.properties` (cùng Wrapper JAR).
- **Maven:** `mvnw`, `mvnw.cmd` và `.mvn/wrapper/maven-wrapper.properties`.

Lần đầu, Wrapper có thể tải bản phân phối và dependency rồi lưu cache; lần sau thường nhanh hơn. Nếu mạng chậm, việc dừng ở bước `Downloading` không tự động là lỗi Java.

Trong **Windows PowerShell**, dùng tiền tố `./` theo cú pháp Windows là `.\` để gọi script ở thư mục hiện tại: ví dụ `.\gradlew.bat` hoặc `.\mvnw.cmd`. Trong **Command Prompt (cmd.exe)** có thể gọi `gradlew.bat` hoặc `mvnw.cmd` trực tiếp. Trên **Linux**, dùng `./gradlew` hoặc `./mvnw`; tiền tố `./` là cần thiết khi thư mục hiện tại không nằm trong `PATH`.

## 4. Lần build đầu tiên với Gradle

Thực hiện phần này khi dự án có file `build.gradle` hoặc `build.gradle.kts`.

### 4.1 Windows PowerShell

Ví dụ thư mục dự án là `C:\work\demo`; thay bằng đường dẫn thật:

~~~powershell
cd C:\work\demo
java -version
javac -version
.\gradlew.bat --version
.\gradlew.bat clean build
Get-ChildItem .\build\libs\
~~~

Lệnh `--version` cho biết Gradle và JVM Wrapper thực sự đang dùng. `clean` xóa sản phẩm build cũ trong thư mục output của dự án; `build` chạy các task thuộc vòng đời build, thường gồm biên dịch, test và đóng gói đối với dự án Java/Spring Boot thông thường.

Nếu sử dụng Windows **Command Prompt** thay PowerShell:

~~~bat
cd /d C:\work\demo
gradlew.bat --version
gradlew.bat clean build
dir build\libs
~~~

`cd /d` còn cho phép đổi ổ đĩa khi cần.

### 4.2 Linux (bash)

~~~bash
cd ~/work/demo
java -version
javac -version
./gradlew --version
./gradlew clean build
ls -lh build/libs/
~~~

Nếu shell trả `Permission denied` khi gọi script, xác nhận bạn đang ở đúng thư mục rồi cấp quyền chạy **một lần**:

~~~bash
chmod +x gradlew
./gradlew clean build
~~~

Nếu không có thư mục `build/libs/`, hãy xem output task thực tế: dự án dạng thư viện, module cha hoặc build tùy biến có thể tạo artifact ở vị trí khác hoặc không có task `bootJar`.

### 4.3 Cách đọc output Gradle

Ví dụ một lần build thành công có thể kết thúc bằng:

~~~text
> Task :compileJava
> Task :test
> Task :bootJar

BUILD SUCCESSFUL in ...
~~~

Đây là **log minh họa**, không phải stdout cố định. Các task hiển thị phụ thuộc project, Gradle có thể ghi `UP-TO-DATE` hoặc `FROM-CACHE` và thời gian sẽ thay đổi. Điểm quan trọng là dòng `BUILD SUCCESSFUL` cùng mã thoát thành công.

Với cấu hình Spring Boot Gradle plugin và Java plugin thông thường, task `bootJar` tạo JAR thực thi trong `build/libs/`; có thể có thêm JAR `-plain.jar` không chứa các dependency cần thiết để chạy như Spring Boot executable JAR. Chọn đúng artifact đã tạo, không đoán mọi tên JAR đều chạy được bằng `java -jar`.

## 5. Lần build đầu tiên với Maven

Thực hiện phần này khi dự án có `pom.xml`. Các lệnh dưới đây là **lựa chọn thay thế** cho Gradle, không phải bước bắt buộc phải chạy thêm sau Gradle.

### 5.1 Windows PowerShell

~~~powershell
cd C:\work\demo
java -version
javac -version
.\mvnw.cmd --version
.\mvnw.cmd clean package
Get-ChildItem .\target\
~~~

Với **Command Prompt**:

~~~bat
cd /d C:\work\demo
mvnw.cmd --version
mvnw.cmd clean package
dir target
~~~

### 5.2 Linux (bash)

~~~bash
cd ~/work/demo
java -version
javac -version
./mvnw --version
./mvnw clean package
ls -lh target/
~~~

Nếu cần cấp quyền chạy script:

~~~bash
chmod +x mvnw
./mvnw clean package
~~~

`clean` xóa output Maven cũ (thông thường là `target/`). `package` chạy các giai đoạn Maven trước nó, gồm biên dịch và unit test theo cấu hình thông thường, rồi tạo artifact. `verify` đi xa hơn `package` trong lifecycle; `install` đưa artifact vào local Maven repository và **không cần cho lần build đầu tiên**.

### 5.3 Cách đọc output Maven

Ví dụ phần cuối của một build thành công:

~~~text
[INFO] --- maven-compiler-plugin:...:compile ...
[INFO] --- maven-surefire-plugin:...:test ...
[INFO] --- maven-jar-plugin:...:jar ...
[INFO] BUILD SUCCESS
~~~

Đây chỉ là **minh họa cấu trúc log**; plugin, thứ tự và số lượng dòng thực tế phụ thuộc `pom.xml`. Với `spring-boot-maven-plugin` được cấu hình thực hiện `repackage`, JAR chính trong `target/` có thể là JAR Spring Boot thực thi. Nếu plugin không được khai báo hoặc không gắn vào lifecycle, một file `.jar` Maven tạo ra có thể là JAR Java thông thường, không chạy độc lập bằng `java -jar`.

## 6. Xác nhận kết quả: build thành công, artifact, chạy thử

Ba lớp xác nhận cần phân biệt:

| Mức | Bằng chứng | Kết luận |
| --- | --- | --- |
| 1. Build | Gradle hiện `BUILD SUCCESSFUL` hoặc Maven hiện `BUILD SUCCESS`, tiến trình trả exit code `0` | Quy trình build đã hoàn tất theo cấu hình và các kiểm tra được chạy |
| 2. Artifact | Có file JAR/WAR đúng tại `build/libs/` hoặc `target/` (nếu project đóng gói) | Đã tạo sản phẩm đóng gói |
| 3. Runtime (tùy chọn) | Ứng dụng khởi động và log không có lỗi khởi động | Artifact có thể chạy với cấu hình/môi trường hiện tại |

Để **chạy thử JAR thực thi**, trước tiên liệt kê artifact và thay tên file trong lệnh sau bằng **tên thực tế** vừa thấy. Đây là ví dụ tên file, không phải đường dẫn cố định cho mọi dự án:

~~~powershell
# Windows PowerShell: chọn một trong hai, tùy dự án Gradle hay Maven
java -jar .\build\libs\demo-0.0.1-SNAPSHOT.jar
java -jar .\target\demo-0.0.1-SNAPSHOT.jar
~~~

~~~bash
# Linux: chọn một trong hai, tùy dự án Gradle hay Maven
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar
java -jar target/demo-0.0.1-SNAPSHOT.jar
~~~

**Chỉ chạy một lệnh phù hợp.** Không dùng `java -jar build/libs/*.jar` như một lệnh chung cho cả Windows và Linux: wildcard có thể không được shell mở rộng theo cách bạn mong đợi, và thư mục có thể chứa cả JAR thường lẫn Boot JAR.

Nếu dự án là Spring Boot web app có server nhúng và không cấu hình port khác, thường sẽ thấy thông báo khởi động thành công và server lắng nghe port 8080. Tuy nhiên app không có web starter có thể hoàn tất rồi thoát, và web app không định nghĩa route `/` có thể trả HTTP 404 dù server vẫn chạy. Kiểm tra endpoint **thực sự được khai báo**; dừng app đang chạy bằng `Ctrl+C`.

Có thể chạy trong chế độ phát triển mà chưa tạo file JAR với Gradle `bootRun` hoặc Maven `spring-boot:run`, nếu plugin tương ứng được áp dụng:

~~~powershell
# Windows PowerShell: chọn một
.\gradlew.bat bootRun
.\mvnw.cmd spring-boot:run
~~~

~~~bash
# Linux: chọn một
./gradlew bootRun
./mvnw spring-boot:run
~~~

Đây là **lệnh chạy ứng dụng**, không thay cho việc kiểm tra `clean build` hoặc `clean package`. Một dự án nhiều module có thể cần chạy task/goal tại module ứng dụng cụ thể.

## 7. Lỗi thường gặp trong lần build đầu

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/xử lý |
| --- | --- | --- |
| Windows: `java` không được nhận diện; Linux: `java: command not found` | Chưa cài JDK hoặc `PATH` sai | Cài đúng JDK, chỉnh `JAVA_HOME` và `PATH`, mở terminal mới; thử `java -version`, `javac -version` |
| Wrapper không tìm thấy | Đang sai thư mục hoặc dự án không có Wrapper | Về thư mục chứa `pom.xml`/`build.gradle`; kiểm tra script `mvnw.cmd`/`gradlew.bat` hoặc `mvnw`/`gradlew`; chỉ khi dự án không cung cấp Wrapper mới cân nhắc bản Maven/Gradle cài sẵn đúng phiên bản |
| Linux: `Permission denied` | Script không có quyền thực thi | `chmod +x gradlew` hoặc `chmod +x mvnw`, rồi chạy lại |
| Linux: `/bin/sh^M` hoặc `bad interpreter` | Script shell bị chuyển line ending sang CRLF | Khôi phục file script chuẩn với LF từ nguồn dự án; kiểm tra cấu hình Git line endings, không chỉnh sửa lung tung Wrapper JAR |
| `JAVA_HOME is set to an invalid directory`, `invalid source release`, lỗi JVM/Gradle không tương thích | `JAVA_HOME`, toolchain hoặc bản Gradle/JDK không khớp yêu cầu | Đối chiếu `java -version`, Wrapper `--version` và cấu hình Java của project; dùng bộ phiên bản tương thích đã được dự án khai báo |
| `Could not resolve`, `Connection timed out`, tải distribution/dependency thất bại | Mạng, DNS, proxy, mirror hoặc repository bị chặn | Kiểm tra Internet/proxy, URL Wrapper, repository và cache; không mặc định quy lỗi cho source code |
| `Compilation failed` / `COMPILATION ERROR` | Lỗi source, dependency hoặc cấu hình compiler | Đọc dòng lỗi đầu tiên có file, dòng, nguyên nhân; sửa rồi build lại |
| `There were failing tests` / `Tests run: ..., Failures: ...` | Test không đạt hoặc thiếu môi trường test | Xem `build/reports/tests/test/` hay `target/surefire-reports/`, sửa test/fixture hoặc cấu hình phù hợp; đừng xem bỏ test là build đã được kiểm chứng đầy đủ |
| Có JAR nhưng `no main manifest attribute` hoặc `ClassNotFoundException` | Chọn nhầm plain JAR, thiếu plugin đóng gói Spring Boot hoặc thiếu main class | Dùng đúng Boot JAR và kiểm tra `bootJar`/Spring Boot Maven `repackage` cùng main class |
| Build xong nhưng khi run báo `Port 8080 was already in use` hay thiếu biến môi trường | Lỗi runtime/configuration, không phải lỗi biên dịch | Đổi port, dừng tiến trình chiếm port hoặc cung cấp cấu hình yêu cầu; xác nhận lại bằng log khởi động |

Khi lỗi xảy ra, giữ nguyên thông báo lỗi đầy đủ, phân biệt lỗi **thiết lập môi trường → tải dependency → compile → test → package → runtime**. Với Gradle có thể chạy `./gradlew build --stacktrace` trên Linux hoặc `.\gradlew.bat build --stacktrace` trên Windows để xem thêm stack trace; Maven dùng `./mvnw -e package` hoặc `.\mvnw.cmd -e package`. Không thay đổi hàng loạt version chỉ vì một lỗi chưa được phân loại.

## 8. Bài thực hành và tiêu chí tự kiểm tra

1. Chọn **một** dự án Spring Boot có Wrapper. Ghi lại công cụ build, JDK được yêu cầu và thư mục gốc.
2. Mở PowerShell/cmd trên Windows hoặc bash trên Linux; chạy `java -version`, `javac -version`, rồi `--version` của Wrapper.
3. Chạy đúng lệnh lần đầu: **Gradle:** `clean build`; **Maven:** `clean package`. Quan sát việc tải công cụ/dependency và những bước compile/test/package.
4. Chỉ coi build đạt khi có thông báo thành công và exit code `0`. Nếu fail, xác định bước nào fail và dùng báo cáo lỗi/test, không đánh dấu thành công.
5. Liệt kê `build/libs/` hoặc `target/`; xác định rõ artifact chính, tránh JAR `plain` hoặc file dự phòng `original`.
6. Nếu đã có executable Spring Boot JAR và app không cần hạ tầng còn thiếu, chạy thử bằng `java -jar`, đọc log và dừng bằng `Ctrl+C`.

Bạn hoàn thành bài khi có thể **lặp lại quy trình trên cả hai hệ điều hành**, giải thích vì sao cần Wrapper, nhận diện đúng artifact và phân biệt kết quả build với việc ứng dụng khởi chạy.

## Tài liệu chính thức để đối chiếu

- [Gradle Wrapper User Guide](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Apache Maven Wrapper](https://maven.apache.org/tools/wrapper/)
- [Spring Boot Gradle plugin: Running Your Application](https://docs.spring.io/spring-boot/gradle-plugin/running.html)
- [Spring Boot Gradle plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
- [Spring Boot Maven plugin documentation](https://docs.spring.io/spring-boot/maven-plugin/)
