# Đọc `mvn --version` để xác định Maven, Java và môi trường thực tế

## 1. Lệnh này cho biết điều gì?

Sau khi cài Maven hoặc mở một dự án mới, chạy:

~~~bash
mvn --version
~~~

Có thể viết ngắn là `mvn -v`. Lệnh in thông tin về **Maven thực sự được gọi trong terminal hiện tại**, **máy ảo Java đang chạy Maven** và **môi trường hệ điều hành**. Đây là bước chẩn đoán đầu tiên khi lệnh build trên máy cá nhân, IDE, CI hoặc máy đồng đội cho kết quả khác nhau.

`mvn --version` không cần `pom.xml` và không biên dịch, chạy test hay đóng gói dự án. Nó cũng không chứng minh dự án sẽ build thành công: yêu cầu JDK của dự án, plugin, dependency và cấu hình toolchain cần được kiểm tra riêng.

> Quan trọng: hãy chạy lệnh trong **đúng terminal hoặc môi trường xảy ra vấn đề**. Kết quả trong Windows PowerShell, WSL, container, terminal của IDE và job CI có thể khác nhau dù chúng cùng nằm trên một máy vật lý.

## 2. Ví dụ kết quả và cách đọc từng dòng

Ví dụ minh họa sau đã lược bỏ mã commit của bản phân phối Maven; các phiên bản và đường dẫn chỉ là giả định:

~~~text
Apache Maven 3.9.9
Maven home: /opt/apache-maven-3.9.9
Java version: 21.0.5, vendor: Eclipse Adoptium, runtime: /opt/jdk-21
Default locale: vi_VN, platform encoding: UTF-8
OS name: "linux", version: "6.8.0", arch: "amd64", family: "unix"
~~~

| Thành phần | Ý nghĩa thực tế | Cần kiểm tra khi nào? |
| --- | --- | --- |
| `Apache Maven 3.9.9` | Phiên bản chương trình Maven đang thực thi; bản phát hành thực thường có thêm thông tin build/commit. | Máy báo lỗi plugin không hỗ trợ phiên bản Maven hoặc CI dùng Maven khác máy cá nhân. |
| `Maven home` | Thư mục cài đặt/bản phân phối Maven đang chạy. | Có nhiều bản Maven, `PATH` trỏ nhầm hoặc wrapper sử dụng bản riêng. |
| `Java version` | Phiên bản JVM dùng để **khởi chạy Maven**. | Plugin cần JDK mới hơn, hoặc Maven đang chạy bằng Java khác dự kiến. |
| `vendor` | Nhà phân phối JVM, ví dụ Eclipse Adoptium, Oracle, Amazon. | Cần đối chiếu chính xác runtime giữa các môi trường. |
| `runtime` | Đường dẫn Java runtime mà tiến trình Maven đang dùng. | Cần biết JVM thực tế có đến từ `JAVA_HOME`/JDK mong muốn không. |
| `Default locale` | Thiết lập locale mặc định của JVM, ảnh hưởng đến một số cách biểu diễn thông báo/số/ngày theo môi trường. | Log khác ngôn ngữ hoặc kết quả công cụ phụ thuộc locale. |
| `platform encoding` | Bảng mã mặc định mà JVM báo trên nền tảng đó. | Gặp lỗi ký tự tiếng Việt, nguồn/đầu ra sai encoding. |
| `OS name`, `version`, `arch`, `family` | Hệ điều hành và kiến trúc mà JVM đang nhìn thấy. | Lỗi script theo OS, thư viện native, hoặc khác biệt Windows/WSL/Linux/container. |

Không nhầm các đường dẫn:

- **`Maven home`** là nơi đặt bản Maven đang chạy, không phải thư mục cache dependency.
- Kho lưu Maven cục bộ thường ở `~/.m2/repository` theo cấu hình mặc định, có thể được đổi trong `settings.xml`; `mvn --version` không cho biết chính xác vị trí kho này.
- **`runtime`** thuộc Java runtime đang chạy Maven; đây cũng không phải thư mục Maven hoặc đường dẫn đến `pom.xml`.

Thông tin ở hai dòng đầu giúp trả lời: *Maven nào đang chạy và nằm ở đâu?* Thông tin Java trả lời: *Maven ấy đang dùng JVM nào?* Dòng OS giúp xác định: *Lệnh được chạy trong môi trường nào?*

## 3. Phân biệt Java chạy Maven, Java biên dịch và phiên bản đích

Đây là khác biệt dễ gây nhầm nhất:

1. **JVM chạy Maven:** chính là `Java version` trong `mvn --version`.
2. **JDK dùng để biên dịch:** thường là JDK của tiến trình Maven, nhưng có thể khác khi dự án cấu hình Maven Toolchains hoặc plugin gọi trình biên dịch khác.
3. **Phiên bản Java của bytecode/API đích:** do cấu hình dự án quyết định, chẳng hạn thuộc tính `maven.compiler.release`.

Ví dụ, kết quả `mvn --version` có thể báo Java 21, trong khi `pom.xml` chứa:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Trong trường hợp này, Maven **chạy trên Java 21** còn trình biên dịch được yêu cầu tạo mã tương thích với **Java 17** khi Maven Compiler Plugin thực thi phù hợp. Việc Java 21 xuất hiện trong `mvn --version` không có nghĩa bytecode của dự án sẽ là Java 21.

Nếu dự án dùng Maven Toolchains, Maven có thể chạy bằng một JDK và tác vụ biên dịch dùng JDK khác. Chỉ đọc `mvn --version` **không đủ để kết luận** JDK compiler, `source`, `target` hoặc `release` cuối cùng. Cần đối chiếu cấu hình `pom.xml`, toolchains và log tác vụ build.

Cũng không nên kết luận có đầy đủ bộ công cụ biên dịch chỉ vì Maven khởi chạy được. Hãy chạy thêm:

~~~bash
java -version
javac -version
~~~

`java -version` báo Java được giải quyết theo lệnh `java` của shell, `javac -version` báo compiler mà shell tìm thấy. Các kết quả này có thể khác JVM thực sự chạy Maven nếu `JAVA_HOME`, `PATH` hoặc script khởi chạy được cấu hình khác nhau.

## 4. Kiểm tra đúng Maven và Java đang được chọn

### Linux/macOS (shell Bash hoặc tương đương)

~~~bash
mvn --version
command -v mvn
command -v java
printf '%s\n' "$JAVA_HOME"
java -version
javac -version
~~~

`command -v` cho biết shell đang tìm thấy lệnh ở đâu; `JAVA_HOME` cho biết đường dẫn được thiết lập, nếu có. So sánh các đường dẫn ấy với `Maven home` và `runtime` trong kết quả Maven. Trên một số hệ thống, đường dẫn lệnh có thể là symlink, vì vậy nó chưa chắc trùng hoàn toàn với đường dẫn cài đặt thực.

### Windows PowerShell

~~~powershell
mvn --version
Get-Command mvn
Get-Command java
$env:JAVA_HOME
java -version
javac -version
~~~

Nếu cần xem tất cả bản thực thi Maven/Java xuất hiện trên `PATH` của Windows, có thể dùng:

~~~powershell
where.exe mvn
where.exe java
~~~

Trong PowerShell, dùng `where.exe` để gọi tiện ích của Windows; `where` không kèm `.exe` là bí danh khác của PowerShell. Các công cụ trên là **chẩn đoán**, chưa tự thay đổi biến môi trường.

Khi nhiều JDK được cài song song, kiểm tra xem `JAVA_HOME` có trỏ tới thư mục gốc JDK thích hợp và `PATH` có ưu tiên đúng thư mục `bin` hay không. Sau khi sửa biến môi trường ở cấp hệ thống, hãy mở terminal mới rồi đọc lại `mvn --version`; cửa sổ đang mở có thể vẫn giữ biến môi trường cũ.

## 5. Maven toàn cục và Maven Wrapper không nhất thiết cùng phiên bản

Dự án có thể cung cấp **Maven Wrapper** qua các tệp `mvnw`/`mvnw.cmd` và `.mvn/wrapper/maven-wrapper.properties`. Nếu có wrapper, kiểm tra nó ngay trong thư mục dự án:

~~~bash
./mvnw --version
~~~

Lệnh trên dùng cho Linux/macOS khi script có quyền thực thi. Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd --version
~~~

So sánh kết quả với `mvn --version`:

| Lệnh | Maven được kiểm tra |
| --- | --- |
| `mvn --version` | Bản Maven shell tìm thấy qua `PATH` hoặc cơ chế phân giải lệnh của môi trường. |
| `./mvnw --version` / `.\mvnw.cmd --version` | Bản Maven mà cấu hình wrapper của dự án lựa chọn. |

Nếu hai lệnh hiển thị phiên bản hoặc `Maven home` khác nhau, đó có thể là hành vi **đúng theo thiết kế**. Khi điều tra lỗi build của dự án có wrapper, nên dùng lệnh wrapper mà dự án quy định để kết quả nhất quán hơn giữa các máy. Lần đầu chạy, wrapper có thể cần mạng để tải bản phân phối Maven nếu chưa có trong cache.

Wrapper quản lý **phiên bản Maven**, không tự bảo đảm Maven đang dùng đúng JDK dự án yêu cầu. Vì thế vẫn phải đọc cả dòng `Java version` và `runtime` ở kết quả của wrapper.

## 6. Các tình huống lỗi thường gặp

| Triệu chứng | Cách hiểu | Hướng kiểm tra |
| --- | --- | --- |
| `mvn: command not found` trên Unix hoặc `'mvn' is not recognized` trên Windows | Shell không tìm được lệnh Maven toàn cục. | Kiểm tra Maven đã cài, `PATH`, hoặc dùng wrapper của dự án nếu có. |
| `JAVA_HOME is not defined correctly` hoặc thông báo Java home không hợp lệ | Script Maven không tìm được Java theo cấu hình mong đợi. | Kiểm tra `JAVA_HOME` trỏ tới thư mục JDK/JRE hợp lệ theo yêu cầu Maven, không trỏ thẳng vào tệp `java` hay thư mục `bin`; kiểm tra lại runtime. |
| `mvn --version` báo Java 17 nhưng dự án/plugin yêu cầu Java 21 | JVM chạy Maven thấp hơn yêu cầu của plugin/build. | Điều chỉnh môi trường chạy Maven rồi đọc lại `Java version`; kiểm tra cấu hình toolchains nếu có. |
| `java -version` và `mvn --version` báo hai phiên bản Java khác nhau | Lệnh `java` của shell và launcher Maven đang chọn runtime khác nhau. | Đối chiếu `JAVA_HOME`, `PATH`, `Get-Command`/`command -v` và `runtime`. |
| Terminal ngoài chạy được, terminal IDE hoặc CI lỗi | Các tiến trình có thể dùng biến môi trường, script, image hoặc JDK khác. | Thu thập `mvn --version` từ chính terminal IDE/job CI bị lỗi và so sánh từng dòng. |
| `mvn --version` báo Linux dù đang dùng PC Windows | Lệnh có thể được chạy trong WSL, container hoặc máy Linux từ xa. | Kiểm tra shell, đường dẫn và nơi chạy lệnh; không mặc định đó là lỗi. |
| Lỗi chữ tiếng Việt hoặc file source mã hóa sai | Encoding/locale có thể khác, nhưng dòng `platform encoding` chỉ là một phần bằng chứng. | Kiểm tra encoding của source, compiler/plugin và JVM; đừng giả định chỉ đổi locale là sửa được mọi lỗi. |

Một số lỗi còn xuất hiện **trước khi in được thông tin phiên bản**, ví dụ Java quá cũ để khởi động bản Maven đang dùng. Trường hợp đó, hãy đọc thông báo lỗi khởi động trước và kiểm tra Java độc lập bằng `java -version`; không thể suy ra một bản Maven đã chạy thành công.

## 7. Quy trình đối chiếu khi build lỗi giữa hai môi trường

Giả sử một người build thành công trên máy cá nhân nhưng job CI thất bại. Thu thập trong **mỗi môi trường**:

1. Kết quả `mvn --version` (hoặc lệnh wrapper mà dự án dùng).
2. `java -version` và `javac -version` nếu có compiler.
3. Đường dẫn lệnh Maven/Java và `JAVA_HOME` (tránh chụp toàn bộ biến môi trường nếu chứa dữ liệu nhạy cảm).
4. Cấu hình Java đích và Maven Compiler Plugin/Toolchains liên quan trong dự án.

Đối chiếu theo thứ tự: **Maven version → Maven home → Java version/vendor/runtime → OS/arch/encoding → cấu hình build**. Không cần yêu cầu mọi dòng giống hệt: một số khác biệt ở đường dẫn, OS hay vendor có thể chấp nhận được. Mục tiêu là xác định khác biệt nào giải thích lỗi cụ thể.

Ví dụ kết luận có bằng chứng: “Máy cá nhân chạy Maven 3.9.9 trên JDK 21, còn CI chạy Maven 3.9.9 trên JDK 17; plugin hiện dùng yêu cầu Java 21”. Với bằng chứng đó, hướng sửa là cấu hình JDK cho job CI, sau đó chạy lại `mvn --version` trong chính job để xác nhận; chỉ đổi thuộc tính `maven.compiler.release` không nâng JVM đang chạy Maven.

## 8. Checklist ghi nhớ

- `mvn --version` trả lời **Maven nào, Java chạy Maven nào, trên môi trường nào**.
- `Maven home` không phải kho dependency `~/.m2/repository`.
- `Java version` không tự xác định phiên bản bytecode hoặc JDK mà Maven Toolchains dùng để compile.
- Kiểm tra `mvn` và `mvnw` riêng nếu dự án có wrapper.
- Khi môi trường khác nhau, so sánh kết quả ngay trong shell/IDE/CI đang build lỗi; sau mỗi thay đổi JDK hay `PATH`, xác nhận lại bằng cùng một lệnh.