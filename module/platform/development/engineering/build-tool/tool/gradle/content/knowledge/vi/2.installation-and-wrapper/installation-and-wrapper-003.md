# Kiểm tra phiên bản Gradle, JVM và môi trường thực thi

## 1. Mục tiêu và điều cần phân biệt

Khi một dự án Gradle chạy được trên máy này nhưng lỗi trên máy khác, câu hỏi “đang dùng phiên bản nào?” thực ra có **nhiều câu trả lời**. Trước khi sửa cấu hình hoặc nâng cấp, hãy xác định:

1. **Gradle của dự án**: phiên bản được Gradle Wrapper chọn từ cấu hình của repository.
2. **Gradle cài toàn cục**: phiên bản được gọi khi nhập lệnh gradle trực tiếp trên máy (nếu có).
3. **JVM chạy Gradle**: JVM khởi chạy client và JVM thực thi build trong Gradle Daemon; hai JVM có thể khác nhau.
4. **JDK dùng để biên dịch/chạy ứng dụng**: có thể được chọn riêng bởi Java Toolchains, không bắt buộc trùng với JVM chạy Gradle.
5. **Môi trường thực thi**: hệ điều hành, kiến trúc CPU, thư mục làm việc, biến môi trường, IDE, CI và cache tải Gradle/JDK.

Một bản chẩn đoán đúng cần ghi lại các thông tin trên **trong chính môi trường gặp lỗi**. Kết quả từ terminal cá nhân không tự động đại diện cho IntelliJ IDEA, container hoặc CI.

## 2. Bắt đầu từ đúng thư mục dự án

Gradle Wrapper là cách chạy Gradle được khuyến nghị vì repository quyết định phiên bản, giúp các thành viên nhóm và CI dùng cùng bản phân phối. Trong thư mục gốc dự án Gradle có các tệp thông thường:

~~~text
project-root/
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── settings.gradle hoặc settings.gradle.kts
└── build.gradle hoặc build.gradle.kts
~~~

Các file build có thể nằm trong module con; lệnh Wrapper cần gọi bằng đường dẫn đúng từ thư mục hiện tại.

**macOS/Linux (shell):**

~~~bash
pwd
ls -l gradlew gradle/wrapper/gradle-wrapper.properties
./gradlew --version
~~~

**Windows (PowerShell):**

~~~powershell
Get-Location
Test-Path .\gradlew.bat
Test-Path .\gradle\wrapper\gradle-wrapper.properties
.\gradlew.bat --version
~~~

Nếu đang ở thư mục con, hãy chuyển về gốc dự án hoặc dùng đường dẫn tương đối đến Wrapper, chẳng hạn ../../gradlew trên macOS/Linux. Trong PowerShell, tiền tố .\ chỉ rõ cần chạy tệp trong thư mục hiện tại.

Ở lần chạy đầu, Wrapper có thể tải bản phân phối Gradle qua mạng rồi lưu cache. Vì vậy lỗi tải ZIP, proxy hoặc DNS là lỗi chuẩn bị môi trường; chưa đủ bằng chứng để kết luận mã nguồn dự án sai.

## 3. Xem phiên bản Gradle thực sự được gọi

### 3.1. Phiên bản của dự án: Wrapper

~~~bash
./gradlew --version
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat --version
~~~

Lệnh này in phiên bản Gradle thực chạy và thông tin môi trường như các thành phần Groovy/Kotlin, JVM và hệ điều hành; nó không chạy các task build. Với các bản Gradle mới, phần JVM có thể tách thành **Launcher JVM** và **Daemon JVM**; các bản cũ có thể hiển thị nhãn **JVM**. Đừng dựa vào vị trí một dòng cố định trong output giữa mọi phiên bản.

Đọc thêm cấu hình mà Wrapper dùng để tải Gradle:

~~~bash
grep '^distributionUrl=' gradle/wrapper/gradle-wrapper.properties
~~~

~~~powershell
Select-String -Path .\gradle\wrapper\gradle-wrapper.properties -Pattern '^distributionUrl='
~~~

Ví dụ, dòng sau chỉ ra bản phân phối Gradle 8.5 được cấu hình:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.5-bin.zip
~~~

File properties mô tả bản phân phối được chỉ định; **kết quả ./gradlew --version là bằng chứng trực tiếp của lần chạy hiện tại**. Kiểm tra cả hai khi nghi ngờ file Wrapper hoặc cache bất thường. Không sửa distributionUrl chỉ để “thử” phiên bản khác trong bước chẩn đoán, vì thay đổi đó ảnh hưởng toàn dự án.

### 3.2. Phiên bản Gradle cài trên máy

~~~bash
gradle --version
~~~

~~~powershell
gradle --version
~~~

Lệnh trên chỉ chạy được khi Gradle đã cài riêng và chương trình gradle có trên PATH. Nếu không tìm thấy lệnh nhưng ./gradlew hoặc .\gradlew.bat chạy được, dự án **không thiếu Gradle**: Wrapper đã đảm nhiệm việc chọn và cung cấp bản phân phối.

Kết quả gradle --version **có thể khác** ./gradlew --version. Với dự án có Wrapper, ưu tiên dùng Wrapper cho build, test, CI và tài liệu hướng dẫn để tránh tình huống hai máy cài Gradle toàn cục khác nhau.

## 4. Kiểm tra Java, JDK và biến môi trường

### 4.1. Kiểm tra Java/Javac trong terminal

**macOS/Linux:**

~~~bash
java -version
javac -version
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
command -v java
command -v javac
command -v gradle
~~~

**Windows PowerShell:**

~~~powershell
java -version
javac -version
$env:JAVA_HOME
Get-Command java
Get-Command javac
where.exe java
where.exe javac
~~~

Cách đọc:

- **java -version** cho biết lệnh java tìm được từ môi trường lệnh hiện tại, thường theo PATH; thông tin phiên bản có thể được in ra luồng lỗi chuẩn (stderr) dù lệnh chạy thành công.
- **javac -version** kiểm tra trình biên dịch Java. Nếu java chạy nhưng javac không tìm thấy, hãy kiểm tra JDK đầy đủ và PATH, thay vì chỉ dựa vào Java Runtime.
- **JAVA_HOME** nên chỉ đến thư mục gốc của một bản cài JDK hợp lệ, ví dụ thư mục chứa bin/java và bin/javac, **không phải** chính thư mục bin hoặc tệp java.
- **command -v** và **Get-Command/where.exe** giúp tìm đường dẫn thực tế đang được gọi. Chỉ xem phiên bản mà không xem đường dẫn có thể bỏ sót xung đột giữa nhiều JDK đã cài.

Nếu JAVA_HOME và PATH trỏ đến hai JDK khác nhau, java -version không nhất thiết phản ánh JDK Wrapper sẽ chọn. Vì vậy cần kết hợp thêm kết quả từ Gradle.

### 4.2. Phân biệt Launcher JVM, Daemon JVM và Toolchain

**Launcher/Client JVM** khởi động lệnh Gradle. Với terminal thông thường, Wrapper ưu tiên JAVA_HOME hợp lệ; nếu không có, nó tìm java qua PATH. **Gradle Daemon JVM** thực thi phần build và có thể được lựa chọn riêng bởi Gradle, IDE hoặc cấu hình của dự án.

Các nguồn cấu hình cần biết:

- **JAVA_HOME**: chọn JDK cho tiến trình khởi chạy từ shell; thường cũng là mặc định của Daemon khi không có cấu hình khác.
- **org.gradle.java.home** trong gradle.properties: có thể chỉ định Java home cho tiến trình Gradle build/Daemon; không thay đổi JVM đã khởi chạy client.
- **gradle/gradle-daemon-jvm.properties**: khi dự án dùng *Daemon JVM criteria*, tiêu chí chọn JVM của Daemon được ưu tiên hơn JAVA_HOME và org.gradle.java.home.
- **IDE Gradle JVM**: IntelliJ IDEA/Eclipse có cấu hình JDK chạy Gradle riêng; kết quả trong IDE có thể khác shell.
- **Java Toolchain**: chọn JDK để biên dịch, kiểm thử hoặc chạy tác vụ Java có hỗ trợ toolchains; không mặc nhiên quyết định JVM chạy Gradle.

Ví dụ cấu hình Groovy DSL sau chọn Java 17 để chạy các công cụ Java có hỗ trợ toolchain:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Đây là **ví dụ cấu hình build.gradle độc lập về cú pháp cho dự án áp dụng Java plugin**, không phải lệnh thực thi ở terminal. Dự án có thể chạy Gradle Daemon trên Java 21 nhưng biên dịch mã nguồn bằng toolchain Java 17. Đừng kết luận máy đang dùng sai JDK chỉ vì java -version và phiên bản toolchain khác nhau.

### 4.3. Xem các JDK mà Gradle tìm được

**macOS/Linux:**

~~~bash
./gradlew -q javaToolchains
./gradlew help --info
~~~

**Windows PowerShell:**

~~~powershell
.\gradlew.bat -q javaToolchains
.\gradlew.bat help --info
~~~

Task javaToolchains giúp liệt kê các bản cài Java mà Gradle phát hiện, gồm phiên bản, đường dẫn và thông tin nhà cung cấp (khả năng và mức chi tiết phụ thuộc phiên bản Gradle/cấu hình). Lệnh help --info cung cấp log chi tiết hơn về việc khởi chạy/chọn Daemon và cấu hình build. Đây là các bước kiểm tra sâu hơn khi output --version và môi trường shell chưa giải thích được lỗi.

Lưu ý: **--version không chứng minh JDK dùng để biên dịch**, và **javaToolchains không có nghĩa mọi task đều dùng cùng một JDK**. Muốn kết luận cho một task cụ thể, cần xem cấu hình toolchain của task đó và log thực thi liên quan.

## 5. Kiểm tra khả năng tương thích Gradle và Java

Gradle cần chạy trên JVM được phiên bản Gradle đó hỗ trợ. Phiên bản Java mới hơn **không tự động** tương thích với Gradle cũ. Một số mốc thực tế:

| Trường hợp | Kết luận |
| --- | --- |
| Gradle 8.5 chạy trên Java 21 | Được hỗ trợ theo bảng tương thích của Gradle. |
| Gradle 8.5 chạy trên Java 22 | Chưa thuộc dải phiên bản hỗ trợ chạy Gradle trên Java 22; hỗ trợ này bắt đầu từ Gradle 8.8. |
| Gradle 9.x chạy Daemon trên Java 8 hoặc 11 | Không phù hợp: từ Gradle 9.0, JVM chạy Gradle Daemon phải là Java 17 trở lên. |
| Build chạy Gradle trên Java 21 nhưng biên dịch code cho Java 17 | Có thể hợp lệ nếu dùng Java Toolchain và plugin/task phù hợp. |

Đối chiếu chính xác từng cặp ở bảng tương thích chính thức: https://docs.gradle.org/current/userguide/compatibility.html. Đối với dự án nhiều plugin (Android Gradle Plugin, Kotlin, Spring Boot...), còn phải kiểm tra **bảng tương thích của từng plugin**, không chỉ bảng của Gradle.

Nếu gặp lỗi liên quan bytecode, plugin hoặc Java version, hãy ghi lại **cả Gradle version, Daemon JVM, Java toolchain và phiên bản plugin có liên quan** trước khi điều chỉnh.

## 6. Kiểm tra môi trường thực thi ngoài phiên bản

Một phiên bản phù hợp vẫn có thể lỗi nếu môi trường khác nhau:

| Thành phần | Cách kiểm tra | Ý nghĩa |
| --- | --- | --- |
| Hệ điều hành và kiến trúc | Phần OS trong --version; thông tin hệ thống của máy/container | Phân biệt Windows, Linux, macOS, x64, ARM64; quan trọng với tool native. |
| Thư mục làm việc | pwd hoặc Get-Location | Xác định đúng Wrapper và project root; tránh gọi nhầm script. |
| JAVA_HOME và PATH | Các lệnh ở mục 4.1 | Phát hiện nhiều JDK và đường dẫn không nhất quán. |
| Gradle User Home | GRADLE_USER_HOME nếu được đặt; mặc định thường là ~/.gradle | Nơi lưu bản phân phối Wrapper, caches và logs của Daemon. |
| Mạng và proxy | Log lần chạy Wrapper đầu tiên | Xác định lỗi tải Gradle/JDK hoặc truy cập repository là vấn đề môi trường. |
| IDE | Cài đặt Gradle JVM và cấu hình dự án của IDE | Có thể dùng JDK khác terminal. |
| CI/container | Chạy lại các lệnh kiểm tra ngay trong job/container | Không suy đoán phiên bản từ máy phát triển. |

Ví dụ xem vị trí Gradle User Home (giá trị trống nghĩa là chưa đặt biến để ghi đè mặc định):

~~~bash
printf 'GRADLE_USER_HOME=%s\n' "$GRADLE_USER_HOME"
~~~

~~~powershell
$env:GRADLE_USER_HOME
~~~

Có thể kiểm tra các Daemon cùng phiên bản Gradle đang được Gradle quản lý:

~~~bash
./gradlew --status
~~~

~~~powershell
.\gradlew.bat --status
~~~

**--status** liệt kê Daemon đang chạy hoặc đã dừng gần đây của **cùng phiên bản Gradle**; không phải công cụ chứng minh JDK của mọi build hoặc liệt kê toàn bộ Daemon mọi phiên bản. Khi cần xác định JDK build thực chạy, ưu tiên thông tin Daemon JVM và log --info.

## 7. Tình huống lỗi phổ biến và hướng xử lý

### 7.1. Không chạy được gradle nhưng Wrapper chạy được

**Dấu hiệu:** gradle: command not found hoặc gradle không được nhận diện là lệnh. **Nguyên nhân thường gặp:** chưa cài Gradle toàn cục hoặc PATH không chứa nó. **Cách xử lý:** dùng ./gradlew (macOS/Linux) hoặc .\gradlew.bat (Windows) trong dự án có Wrapper. Không cần cài bản Gradle toàn cục chỉ vì lỗi này.

### 7.2. Wrapper báo không tìm thấy Java hoặc JAVA_HOME sai

**Dấu hiệu:** java không tìm thấy hoặc thông báo JAVA_HOME trỏ tới thư mục không hợp lệ. **Kiểm tra:** java -version, javac -version, JAVA_HOME và đường dẫn java thực tế. **Cách xử lý:** cài/chọn JDK tương thích; thiết lập JAVA_HOME đến gốc JDK, đảm bảo PATH có thể tìm java khi cần; mở terminal mới để nhận biến môi trường vừa cập nhật. Sau đó chạy lại Wrapper --version.

### 7.3. Gradle và JDK không tương thích

**Dấu hiệu:** build từ chối Java version, JVM quá cũ/mới hoặc gặp lỗi từ plugin khi dùng JDK mới. **Kiểm tra:** Wrapper --version, Daemon JVM, compatibility matrix và phiên bản plugin. **Cách xử lý:** chọn JDK mà phiên bản Gradle hiện tại hỗ trợ hoặc lên kế hoạch nâng cấp Wrapper/plugin có kiểm thử. Không thay đổi bản Gradle của nhóm một cách tùy tiện trong bước chẩn đoán.

### 7.4. Terminal chạy được nhưng IDE hoặc CI lỗi

**Dấu hiệu:** cùng repository nhưng IDE/CI hiển thị Java hoặc Gradle khác. **Kiểm tra:** chạy Wrapper --version và java -version trong cả hai môi trường, so sánh JAVA_HOME, Gradle JVM trong IDE, cấu hình image/container/JDK của CI và Java Toolchains. **Cách xử lý:** cấu hình đúng JDK cho từng vai trò; ưu tiên Wrapper nhất quán trên máy và CI.

### 7.5. Wrapper thiếu tệp hoặc không tải được bản phân phối

**Dấu hiệu:** thiếu gradle-wrapper.jar, không tìm thấy GradleWrapperMain, lỗi tải distribution hoặc lỗi certificate/proxy. **Kiểm tra:** đủ bộ file Wrapper, distributionUrl và log kết nối. **Cách xử lý:** khôi phục Wrapper chuẩn từ version control hoặc quy trình được dự án duyệt; kiểm tra network/proxy/checksum. Không tải JAR lạ từ nguồn không được xác minh.

### 7.6. Script không có quyền thực thi trên Unix

**Dấu hiệu:** permission denied khi chạy ./gradlew. Kiểm tra quyền tệp bằng ls -l gradlew. Nếu tệp đúng là Wrapper của dự án nhưng thiếu bit thực thi, có thể dùng chmod +x gradlew theo quy trình repository rồi chạy lại. Windows dùng gradlew.bat nên không áp dụng cách sửa quyền Unix này.

## 8. Quy trình kiểm tra nhanh trước khi báo lỗi

Làm lần lượt trong **đúng môi trường gây lỗi**:

1. Xác định gốc repository và sự hiện diện của các tệp Wrapper.
2. Chạy Wrapper --version và ghi lại phiên bản Gradle, phần JVM, hệ điều hành.
3. Xem distributionUrl, đối chiếu với bản Wrapper đang chạy; chỉ dùng gradle --version nếu cần so sánh Gradle toàn cục.
4. Chạy java -version, javac -version; kiểm tra JAVA_HOME, PATH và JDK thực tế.
5. Nếu chưa rõ, chạy Wrapper -q javaToolchains và Wrapper help --info để tìm JDK/toolchain/Daemon liên quan.
6. Đối chiếu Gradle–JVM và phiên bản plugin với tài liệu tương thích; thử lại lệnh build gây lỗi, giữ log lỗi nguyên văn.

**Ví dụ phân tích:** máy có Gradle toàn cục 9.x, nhưng repository dùng Wrapper 8.5. Lệnh gradle --version có thể báo 9.x, trong khi ./gradlew --version báo 8.5; build chuẩn của repository vẫn phải dùng Wrapper 8.5. Nếu terminal dùng Java 21 và build chọn toolchain Java 17, đây có thể là cấu hình hợp lệ: Java 21 chạy Gradle, còn Java 17 phục vụ biên dịch. Chỉ coi đó là lỗi khi phiên bản, plugin hoặc nhiệm vụ thực tế yêu cầu khác.

Khi gửi lỗi cho đồng đội, cung cấp lệnh đã chạy, thư mục làm việc, hệ điều hành, phiên bản Wrapper, Launcher/Daemon JVM, JAVA_HOME, toolchain có liên quan và đoạn log đầu tiên chỉ ra nguyên nhân. Tránh gửi chỉ một dòng “Gradle build failed”, vì nó không đủ thông tin để tái hiện.

## 9. Nguồn tra cứu chính thức

- Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Gradle Daemon và lựa chọn JVM: https://docs.gradle.org/current/userguide/gradle_daemon.html
- Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Build environment và org.gradle.java.home: https://docs.gradle.org/current/userguide/build_environment.html
- Ma trận tương thích Java/Gradle: https://docs.gradle.org/current/userguide/compatibility.html

Các trang sử dụng nhánh tài liệu hiện hành; với dự án đang dùng Gradle cũ, nên mở **bản tài liệu theo đúng phiên bản Wrapper** để đối chiếu chi tiết hành vi của release đó.