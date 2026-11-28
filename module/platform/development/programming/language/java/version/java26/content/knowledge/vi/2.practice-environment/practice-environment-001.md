# Kiểm tra JDK của terminal, IDE, build và kiểm thử

Một dự án Java có thể dùng nhiều JDK trong cùng một lần làm việc: terminal chọn lệnh java qua PATH, IDE có JDK của project, Maven hoặc Gradle có JVM chạy chính công cụ build và toolchain biên dịch riêng, còn tiến trình kiểm thử có thể chạy bằng một JVM khác. Vì vậy, thấy java --version trả về đúng phiên bản chưa đủ để kết luận toàn bộ môi trường đang dùng đúng JDK.

Bài thực hành này giúp xác định JDK thực tế ở từng tầng, kiểm tra khả năng biên dịch và chạy chương trình, rồi đồng bộ cấu hình theo phiên bản Java mà project yêu cầu. Các ví dụ dùng Java 26 làm mức đích; nếu project chọn mức khác, thay số 26 bằng phiên bản tương ứng.

## 1. Phân biệt các vị trí chọn JDK

| Thành phần | Vai trò | Cách kiểm tra chính |
|---|---|---|
| JDK cài trên máy | Bộ công cụ phát triển, gồm JVM và các công cụ như java, javac, jshell | Kiểm tra đường dẫn thực thi và JAVA_HOME |
| Terminal | Chạy lệnh theo thứ tự thư mục trong PATH của shell hiện tại | java --version, javac --version, where.exe hoặc type -a |
| IDE | Cung cấp JDK cho phân tích mã, biên dịch hoặc chạy ứng dụng theo cấu hình của IDE | Project SDK, module SDK, compiler và run configuration |
| Maven/Gradle | JVM chạy chính công cụ build; có thể chọn JDK biên dịch riêng qua toolchain | mvnw -v, gradlew --version, cấu hình toolchain |
| JVM chạy test | JVM thực thi các test; có thể khác JVM chạy Maven/Gradle | Kiểm tra java.home và java.version ngay trong test |

JDK là lựa chọn phù hợp cho môi trường phát triển. Các bản JDK hiện đại đã chứa runtime cần thiết để chạy ứng dụng Java; không cần tìm một gói JRE độc lập cho quy trình phát triển thông thường.

Ba khái niệm cần phân biệt:

- JAVA_HOME là biến môi trường trỏ đến thư mục gốc của JDK. Đường dẫn không kết thúc bằng bin.
- PATH quyết định shell tìm thấy chương trình java hoặc javac nào trước. Nếu một JDK khác đứng trước JAVA_HOME/bin, lệnh java vẫn có thể chạy JDK đó.
- Toolchain là cấu hình của build để chọn JDK cho tác vụ biên dịch hoặc chạy test. Toolchain có thể khác JDK đang chạy chính Maven hoặc Gradle.

## 2. Xác định JDK mà terminal đang sử dụng

Mở một terminal mới sau khi cài JDK hoặc thay đổi biến môi trường. Chạy các lệnh sau và ghi lại phiên bản cùng đường dẫn trả về.

### Windows PowerShell

~~~powershell
java --version
javac --version

$env:JAVA_HOME
Get-Command java, javac -All | Format-Table Name, CommandType, Source -AutoSize
where.exe java
where.exe javac

$env:Path -split ';'

java -XshowSettings:properties -version 2>&1 |
    Select-String 'java.home|java.version|java.vendor'
~~~

Get-Command cho biết PowerShell đang phân giải tên lệnh ra sao; where.exe liệt kê các executable tìm được trong PATH. Nếu có nhiều kết quả, shell thường dùng kết quả đứng đầu. So sánh đường dẫn đó với thư mục JDK mà JAVA_HOME trỏ tới.

### Linux và macOS (Bash/Zsh)

~~~sh
java --version
javac --version

printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
type -a java
type -a javac
printf '%s\n' "$PATH" | tr ':' '\n'

java -XshowSettings:properties -version 2>&1 |
    grep -E 'java.home|java.version|java.vendor'
~~~

Trên macOS, có thể liệt kê các JDK mà hệ thống nhận diện bằng lệnh:

~~~sh
/usr/libexec/java_home -V
~~~

java.home cho biết thư mục runtime thực tế của JVM vừa khởi chạy. Kết hợp thông tin này với đường dẫn java và javac để phát hiện trường hợp runtime và compiler đến từ hai bản JDK khác nhau.

### Cách đọc kết quả

- java --version xác nhận phiên bản JVM được gọi từ terminal.
- javac --version xác nhận phiên bản compiler được gọi từ terminal.
- java.vendor cho biết nhà cung cấp bản JDK.
- java.home cho biết vị trí runtime đang chạy.
- JAVA_HOME cho biết giá trị biến môi trường, nhưng tự nó không chứng minh lệnh java đang dùng đúng thư mục đó.

Nếu java và javac khác phiên bản, hãy kiểm tra thứ tự PATH và các bản JDK được cài. Đặt JAVA_HOME trỏ đến thư mục gốc JDK mong muốn, đưa thư mục bin tương ứng lên trước trong PATH, mở terminal mới rồi kiểm tra lại. Tránh chỉ sửa biến môi trường trong một cửa sổ terminal và cho rằng IDE hoặc tiến trình build đã tự nhận cấu hình mới.

## 3. Biên dịch và chạy một chương trình kiểm tra

Tạo file EnvCheck.java với nội dung:

~~~java
public class EnvCheck {
    public static void main(String[] args) {
        System.out.println("Runtime version: " + Runtime.version());
        System.out.println("Java version: " + System.getProperty("java.version"));
        System.out.println("Java home: " + System.getProperty("java.home"));
        System.out.println("Java vendor: " + System.getProperty("java.vendor"));
    }
}
~~~

Tạo thư mục đầu ra rồi biên dịch với mức phát hành Java 26:

~~~sh
mkdir -p out
javac --release 26 -d out EnvCheck.java
java -cp out EnvCheck
~~~

Trong PowerShell, có thể tạo thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force out
javac --release 26 -d out EnvCheck.java
java -cp out EnvCheck
~~~

Kết quả cho biết compiler có biên dịch được mã với API và mức bytecode của Java 26 hay không, đồng thời cho biết JVM thực tế đang chạy chương trình. Lệnh javac --release 26 cần một compiler hỗ trợ release 26, thường là JDK 26 hoặc JDK mới hơn có hỗ trợ mức release này.

--release giúp ràng buộc phiên bản ngôn ngữ, bytecode và API Java SE được phép sử dụng khi biên dịch. Nó không tự chọn JVM để chạy chương trình. Vì vậy, nếu biên dịch thành công nhưng chạy bằng runtime quá cũ, ứng dụng vẫn có thể thất bại. Lệnh java -version và kết quả java.home khi chạy chương trình là hai phép kiểm tra riêng cần thực hiện.

Với mã nguồn Java 26 dùng tính năng preview, phải dùng JDK của đúng bản phát hành đó và bật preview ở cả bước biên dịch lẫn chạy. Trong ví dụ thực tế, thay EnvCheck.java bằng lớp có sử dụng cú pháp hoặc API preview của bài tập; các lệnh sau minh họa cách truyền cờ:

~~~sh
javac --enable-preview --release 26 -d out EnvCheck.java
java --enable-preview -cp out EnvCheck
~~~

Các cờ preview cần được truyền tương ứng cho compiler và JVM chạy test nếu test sử dụng tính năng preview. Preview của một bản phát hành gắn với chính bản phát hành đó; không thể lấy cờ preview của JDK 26 để bật tính năng preview Java 26 trên một JDK phát hành sau. Chỉ bật preview khi bài học hoặc project thực sự yêu cầu; mã dùng tính năng đã chính thức hóa không cần cờ này.

Với API incubator như Vector API, kiểm tra module có trong đúng JDK đang dùng và truyền tùy chọn `--add-modules` cho compiler, JVM chạy ứng dụng và JVM chạy test theo tài liệu của bản JDK đó. Ví dụ, module Vector API có tên `jdk.incubator.vector` ở các bản phát hành cung cấp API này. Tên module, API và trạng thái incubator có thể thay đổi giữa các bản JDK; `--release` không biến API incubator thành API Java SE ổn định. Chỉ dựa vào tài liệu của JDK mục tiêu và giữ JDK biên dịch, chạy, kiểm thử tương thích với module được chọn.

## 4. Đối chiếu JDK trong IDE

IDE có thể lưu cấu hình riêng, nên kết quả trong terminal không đại diện cho cấu hình của project. Kiểm tra cả JDK dùng cho project, build tool và từng cấu hình chạy.

### IntelliJ IDEA

Kiểm tra các vị trí sau:

1. **Project Structure → Project**: xem Project SDK và mức ngôn ngữ.
2. **Project Structure → Modules**: kiểm tra SDK của module nếu module có cấu hình riêng.
3. **Settings → Build, Execution, Deployment → Build Tools → Gradle**: kiểm tra Gradle JVM khi project dùng Gradle.
4. **Settings → Build Tools → Maven → Runner**: kiểm tra JRE dùng để chạy Maven.
5. **Run/Debug Configurations**: kiểm tra JRE của cấu hình chạy ứng dụng hoặc test.

Project SDK, Gradle JVM và JRE trong run configuration có mục đích khác nhau. Không nên suy ra tất cả đều đồng bộ chỉ từ một trường Project SDK.

### Visual Studio Code

Với Java Extension Pack, kiểm tra cấu hình runtime trong Settings hoặc settings.json:

- java.jdt.ls.java.home chọn JDK chạy Java language server.
- java.configuration.runtimes khai báo các JDK có thể dùng cho project và mức Java tương ứng.

JDK chạy language server không mặc nhiên là JVM dùng để chạy ứng dụng. Nếu project dùng Maven hoặc Gradle, tiếp tục kiểm tra wrapper và toolchain của build.

### Eclipse

Trong **Preferences → Java → Installed JREs**, khai báo JDK đã cài và chọn bản phù hợp. Kiểm tra thêm:

- **Java → Compiler**: mức tuân thủ của compiler.
- **Java → Installed JREs → Execution Environments**: ánh xạ môi trường Java với JDK đã khai báo.
- **Run Configurations → JRE**: runtime của ứng dụng hoặc test.

Sau khi thay đổi cấu hình, build lại project và chạy một cấu hình thực tế để xác nhận IDE đã dùng đúng JDK.

## 5. Kiểm tra Maven

Dùng Maven Wrapper của project để biết JVM đang chạy Maven:

~~~sh
./mvnw -v
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd -v
~~~

Kết quả hiển thị phiên bản Maven, phiên bản Java và Java home. Ưu tiên wrapper được lưu cùng project để các thành viên và CI dùng cùng phiên bản Maven. Lệnh mvn -v chỉ kiểm tra Maven cài toàn máy; kết quả có thể khác wrapper. Đảm bảo phiên bản Maven Wrapper và các plugin của project tương thích với JDK đã chọn.

Đặt mức Java mục tiêu trong pom.xml bằng thuộc tính maven.compiler.release:

~~~xml
<properties>
    <maven.compiler.release>26</maven.compiler.release>
</properties>
~~~

Đảm bảo project dùng phiên bản maven-compiler-plugin hỗ trợ thuộc tính release. Khi cần chọn một JDK biên dịch khác JVM chạy Maven, cấu hình Maven Toolchains và toolchain tương ứng theo hướng dẫn của phiên bản plugin đang dùng. Khi đó, hãy phân biệt:

- JVM của Maven: thể hiện trong kết quả mvnw -v.
- JDK được compiler plugin chọn: phụ thuộc cấu hình toolchain.
- JVM chạy test: thường theo môi trường Maven đang chạy, trừ khi cấu hình plugin hoặc toolchain chọn JVM khác.

Nếu build thành công nhưng test chạy trên JDK không mong muốn, kiểm tra cấu hình Surefire/Failsafe, fork JVM và toolchain liên quan thay vì chỉ đổi JAVA_HOME.

## 6. Kiểm tra Gradle

Dùng Gradle Wrapper của project:

~~~sh
./gradlew --version
~~~

Trên Windows:

~~~powershell
.\gradlew.bat --version
~~~

Kết quả cung cấp thông tin Gradle, Launcher JVM và Daemon JVM. Trong IDE, Gradle JVM có thể được chọn riêng. Nếu project dùng Java plugin và Gradle hỗ trợ toolchain, có thể xem các JDK được phát hiện bằng:

~~~sh
./gradlew javaToolchains
~~~

Trong build.gradle.kts, cấu hình toolchain cho tác vụ Java và mức API/bytecode mục tiêu:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(26)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 26
}
~~~

Toolchain chọn JDK cho compiler. options.release giới hạn API và phiên bản Java mục tiêu. Hai cấu hình này giải quyết hai việc liên quan nhưng không thay thế nhau. Gradle Daemon vẫn cần một JVM tương thích với phiên bản Gradle đang dùng; hãy kiểm tra ma trận tương thích Gradle–JDK và phiên bản plugin của project khi nâng cấp.

Nếu muốn chỉ định rõ JVM cho test task, có thể cấu hình launcher:

~~~kotlin
tasks.withType<Test>().configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(26)
    }
}
~~~

Sau khi đổi cấu hình, chạy lại wrapper và kiểm tra log của tác vụ. Nếu Gradle chạy từ IDE, kiểm tra Gradle JVM trong IDE vì nó có thể khác terminal. Cũng cần phân biệt JVM của Gradle Daemon với JDK toolchain mà compiler hoặc test task sử dụng.

## 7. Xác minh JVM thực thi test

Một dự án có thể biên dịch bằng JDK 26 nhưng chạy test trên một JDK khác. Để xác định JVM thực tế, thêm tạm các dòng sau vào một test đang chạy:

~~~java
System.out.println("test java.version = " + System.getProperty("java.version"));
System.out.println("test java.home = " + System.getProperty("java.home"));
System.out.println("test java.vendor = " + System.getProperty("java.vendor"));
System.out.println("test feature = " + Runtime.version().feature());
~~~

Chạy test bằng đúng cách thường dùng: từ terminal qua wrapper và từ IDE nếu nhóm phát triển sử dụng cả hai. Đối chiếu kết quả giữa hai lần chạy. Nếu hệ thống test đang thu stdout, bật hiển thị standard output tạm thời theo cấu hình của test runner hoặc dùng debugger để xem các giá trị.

Với Gradle, kiểm tra launcher của task Test. Với Maven, kiểm tra cấu hình Surefire/Failsafe, chế độ fork và toolchain nếu có. Khi test chạy trong CI, ghi nhận phiên bản Java và đường dẫn JDK ngay trong job để phát hiện khác biệt giữa máy cá nhân và môi trường CI.

## 8. Chẩn đoán các trường hợp thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| java --version và javac --version khác nhau | PATH trỏ tới nhiều JDK hoặc hai executable đến từ hai vị trí khác nhau | Kiểm tra where.exe/type -a, thứ tự PATH và JAVA_HOME |
| Terminal đúng JDK nhưng IDE sai | IDE đang giữ Project SDK, module SDK hoặc run configuration cũ | Kiểm tra từng cấu hình JDK trong IDE rồi chạy lại |
| mvnw -v khác java --version | Maven được khởi chạy bằng JDK khác với lệnh java trong terminal | Kiểm tra Java home trong kết quả Maven và cấu hình runner/toolchain |
| gradlew --version khác java --version | Gradle Daemon hoặc Gradle JVM trong IDE dùng JDK khác | Kiểm tra Launcher JVM, Daemon JVM và org.gradle.java.home nếu được đặt |
| Build biên dịch được nhưng ứng dụng báo UnsupportedClassVersionError | JVM chạy ứng dụng cũ hơn mức bytecode đã biên dịch | Kiểm tra JVM của run configuration, container hoặc máy triển khai |
| Biên dịch thất bại vì API không tồn tại ở mức release | Mã đang gọi API mới hơn mức --release đã chọn | Kiểm tra API cần dùng và chọn mức release đúng với yêu cầu triển khai |
| Test chạy khác kết quả giữa IDE và terminal | Hai cách chạy chọn JVM, biến môi trường hoặc tham số test khác nhau | In java.version/java.home ngay trong test và đối chiếu cấu hình |
| Project Java 26 không nhận tính năng preview | Thiếu cờ preview hoặc dùng JDK không đúng bản phát hành | Kiểm tra JDK, compiler arguments và JVM arguments của test/run |

Một quy trình chẩn đoán hiệu quả là đi theo thứ tự: xác định executable của terminal, xác định JVM của build tool, xác định JDK toolchain biên dịch, rồi xác định JVM chạy ứng dụng và test. Thay đổi từng cấu hình một và chạy lại phép kiểm tra tương ứng để biết chính xác tầng nào đã được sửa.

## 9. Checklist trước khi bắt đầu một project

- [ ] Đã cài một bản JDK phù hợp với yêu cầu và chính sách hỗ trợ của project.
- [ ] JAVA_HOME trỏ đến thư mục gốc JDK mong muốn.
- [ ] java và javac trong terminal đến từ JDK dự kiến.
- [ ] Đã kiểm tra java.home, java.version và java.vendor.
- [ ] Project SDK, module SDK và run configuration trong IDE đã được kiểm tra.
- [ ] Maven Wrapper hoặc Gradle Wrapper chạy được trên JDK đã chọn.
- [ ] Build tool dùng đúng JDK cho compiler thông qua cấu hình toolchain khi cần.
- [ ] Mức release khớp với Java mục tiêu của project.
- [ ] JVM chạy test đã được xác minh độc lập.
- [ ] Chỉ bật preview hoặc module incubator khi project thực sự cần và đã cấu hình đúng cho compile, run và test.
- [ ] Máy cá nhân và CI dùng cấu hình JDK có thể tái lập; không phụ thuộc vào JDK mặc định tình cờ có trên máy.

Khi hoàn tất các bước này, có thể xác định rõ JDK nào đang được dùng ở từng giai đoạn. Điều đó giúp tránh lỗi do lệch phiên bản giữa compiler và runtime, đồng thời tạo nền tảng ổn định trước khi thực hành các API và tính năng cụ thể của Java 26.
