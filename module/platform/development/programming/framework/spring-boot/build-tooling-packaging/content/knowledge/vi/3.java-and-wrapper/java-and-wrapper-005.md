# Sử dụng Gradle Wrapper qua gradlew và gradlew.bat

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích **Gradle Wrapper** dùng để làm gì và vì sao dự án Spring Boot nên gọi Wrapper thay cho lệnh `gradle` cài toàn cục.
- Phân biệt và chạy đúng **`gradlew` trên Linux/macOS** với **`gradlew.bat` trên Windows**, bao gồm terminal PowerShell và Command Prompt.
- Đọc cấu trúc bốn tệp Wrapper và biết phiên bản Gradle được quyết định ở đâu.
- Dùng Wrapper để xem thông tin Gradle, liệt kê task, build, test, chạy Spring Boot và tạo executable JAR.
- Hiểu cách Wrapper tải/cached Gradle, quản lý JDK, chạy trong CI và nâng cấp phiên bản Gradle có kiểm soát.
- Chẩn đoán các lỗi về đường dẫn, quyền thực thi, JDK, mạng, thiếu file Wrapper và không tương thích phiên bản.

**Bối cảnh:** Trong một dự án Spring Boot sử dụng Gradle, `gradlew` và `gradlew.bat` là hai script do dự án cung cấp để khởi động **phiên bản Gradle mà chính dự án quy định**. Chúng phục vụ cùng mục đích nhưng dành cho hệ điều hành/terminal khác nhau.

## 2. Gradle và Gradle Wrapper khác nhau như thế nào?

**Gradle** là công cụ build: đọc `settings.gradle` hoặc `settings.gradle.kts` cùng `build.gradle` hoặc `build.gradle.kts`, giải quyết dependencies, lập lịch các task (biên dịch, kiểm thử, đóng gói...) rồi thực thi chúng.

**Gradle Wrapper** là lớp khởi động đi kèm dự án. Khi gọi Wrapper, script khởi chạy mã Wrapper trong `gradle-wrapper.jar`; mã này đọc `gradle-wrapper.properties` để chọn đúng bản phân phối Gradle, tải/cài nếu chưa có, sau đó chuyển tiếp các tham số bạn truyền vào Gradle.

~~~text
Người phát triển / CI
        |
        | ./gradlew test      hoặc     .\gradlew.bat test
        v
Script gradlew / gradlew.bat
        |
        v
gradle/wrapper/gradle-wrapper.jar
        |
        | đọc distributionUrl
        v
gradle/wrapper/gradle-wrapper.properties
        |
        | bản Gradle đã cache? -> dùng bản đó
        | chưa có? -> tải ZIP rồi giải nén
        v
Gradle được dự án chỉ định
        |
        | đọc build.gradle(.kts) + settings.gradle(.kts)
        v
Chạy task "test"
~~~

So sánh nhanh:

| Cách chạy | Phiên bản Gradle sử dụng | Điều kiện |
| --- | --- | --- |
| `gradle build` | Bản `gradle` được cài sẵn/tìm thấy trên `PATH` | Máy hoặc CI cần có Gradle phù hợp |
| `./gradlew build` | Bản cấu hình trong Wrapper của **dự án** | Có các tệp Wrapper, Java phù hợp và khả năng tải bản Gradle nếu chưa cache |
| `.\gradlew.bat build` | Cũng là bản cấu hình trong Wrapper của **dự án** | Chạy trong Windows PowerShell, có Java và các tệp Wrapper |

**Lợi ích cốt lõi** là tránh trường hợp máy A dùng Gradle 8, máy B dùng Gradle 9, CI lại dùng phiên bản khác chỉ vì cài Gradle toàn cục khác nhau. Wrapper giúp nhất quán **phiên bản Gradle**, nhưng **không tự đồng bộ JDK, phiên bản plugin, dependencies hoặc cấu hình môi trường**: các thành phần đó vẫn cần quản lý riêng.

## 3. Bốn tệp của Gradle Wrapper

Với một dự án Gradle được tạo từ Spring Initializr, cấu trúc thường có dạng:

~~~text
my-spring-app/
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── settings.gradle             # Hoặc settings.gradle.kts
├── build.gradle                # Hoặc build.gradle.kts
└── src/
    ├── main/
    └── test/
~~~

| Tệp | Vai trò | Có nên commit vào Git? |
| --- | --- | --- |
| `gradlew` | Shell script khởi động Wrapper trên Linux/macOS và môi trường Unix tương thích | **Có** |
| `gradlew.bat` | Batch script khởi động Wrapper trên Windows | **Có** |
| `gradle/wrapper/gradle-wrapper.jar` | Mã bootstrap tải/khởi chạy đúng Gradle | **Có** |
| `gradle/wrapper/gradle-wrapper.properties` | Cấu hình URL, loại distribution, version và tùy chọn download | **Có** |

**Cả bốn tệp Wrapper đều là thành phần nguồn được lưu trong repository.** Không đưa file `gradle-wrapper.jar` vào `.gitignore` chỉ vì nó là file nhị phân: thiếu file này có thể khiến script không hoạt động khi checkout mới hoặc chạy CI.

Cần phân biệt:

- Thư mục `gradle/wrapper/` trong **project** chứa cấu hình và bootstrap, được commit.
- Thư mục `.gradle/` ở **project root** chứa trạng thái/cache cục bộ và thường bị bỏ qua bởi Git.
- Thư mục Gradle user home, mặc định `~/.gradle` trên Linux/macOS hoặc thư mục `.gradle` dưới profile người dùng Windows, lưu distributions/cache dùng lại giữa các dự án; có thể thay đổi qua `GRADLE_USER_HOME`.

Lệnh Wrapper đọc tệp build của project như Gradle thông thường; `gradlew` và `gradlew.bat` **không phải hai hệ build khác nhau** và không tạo ra hai kết quả build chỉ vì tên script khác nhau.

## 4. Chọn lệnh chính xác theo hệ điều hành và terminal

Mở terminal **tại thư mục gốc chứa `gradlew` và `gradlew.bat`**.

### 4.1. Linux và macOS: chạy gradlew

~~~bash
./gradlew --version
./gradlew tasks
./gradlew test
~~~

Tiền tố `./` yêu cầu shell chạy script trong thư mục hiện tại. Tệp `gradlew` cần quyền thực thi; nếu repository được checkout mà thiếu quyền, xem phần lỗi `Permission denied`.

### 4.2. Windows PowerShell: chạy gradlew.bat

~~~powershell
.\gradlew.bat --version
.\gradlew.bat tasks
.\gradlew.bat test
~~~

PowerShell dùng `.\` để gọi tệp trong thư mục hiện tại; gõ đơn thuần `gradlew.bat` có thể không được nhận diện vì PowerShell không mặc định tìm chương trình trong thư mục hiện hành theo cách của CMD.

### 4.3. Windows Command Prompt (cmd.exe)

~~~bat
gradlew.bat --version
gradlew.bat tasks
gradlew.bat test
~~~

Trong CMD, bạn thường có thể chạy `gradlew.bat` trực tiếp khi đang ở đúng thư mục. Dùng `.\gradlew.bat` cũng có thể hợp lệ trong CMD, nhưng ví dụ dùng cách gọi phổ biến nhất.

### 4.4. Git Bash, WSL và terminal tích hợp IDE

- **Git Bash** trên Windows cung cấp shell kiểu Unix, có thể dùng `./gradlew` nếu shell, quyền và Java đều phù hợp; trong PowerShell/CMD thì ưu tiên `gradlew.bat`.
- **WSL** là môi trường Linux chạy trong Windows, nên dùng `./gradlew` và JDK được cài/cấu hình cho WSL. Java cài bên Windows không mặc nhiên là JDK mà Gradle trong WSL dùng.
- **Terminal trong IntelliJ IDEA/VS Code** phụ thuộc shell đang được chọn. Kiểm tra prompt hoặc shell profile để chọn đúng cách gọi.
- **Khi đứng trong thư mục con**, cung cấp đường dẫn tương đối đến script ở project root, ví dụ `../gradlew tasks` khi bạn đang ở đúng một cấp dưới root. Với build nhiều module, thường chạy tại root và chỉ định task theo đường dẫn, ví dụ `./gradlew :service:build` nếu module `service` thật sự tồn tại.

Bảng lệnh tương đương:

| Mục đích | Linux/macOS | Windows PowerShell |
| --- | --- | --- |
| Xem Gradle đang chạy | `./gradlew --version` | `.\gradlew.bat --version` |
| Xem task khả dụng | `./gradlew tasks` | `.\gradlew.bat tasks` |
| Xem mọi task (kể cả ít hiển thị) | `./gradlew tasks --all` | `.\gradlew.bat tasks --all` |
| Chạy test | `./gradlew test` | `.\gradlew.bat test` |
| Build đầy đủ | `./gradlew build` | `.\gradlew.bat build` |
| Dọn kết quả build | `./gradlew clean` | `.\gradlew.bat clean` |
| Chạy ứng dụng Spring Boot | `./gradlew bootRun` | `.\gradlew.bat bootRun` |
| Tạo Spring Boot executable JAR | `./gradlew bootJar` | `.\gradlew.bat bootJar` |

Các task `bootRun` và `bootJar` yêu cầu dự án có áp dụng **Spring Boot Gradle plugin**. Nếu đang ở dự án Java Gradle thông thường chưa có Spring Boot plugin, việc không thấy hai task này là bình thường.

## 5. Ví dụ thực hành: chạy dự án Spring Boot bằng Wrapper

Giả sử bạn đã tạo một project qua **https://start.spring.io** với **Project = Gradle – Groovy** (hoặc Gradle – Kotlin), **Language = Java**, chọn phiên bản Spring Boot/Java tương thích và thêm **Spring Web** nếu cần HTTP endpoint. Giải nén ZIP và mở thư mục gốc bằng terminal.

### Bước 1 — Xác minh Wrapper và JDK

Linux/macOS:

~~~bash
java -version
javac -version
./gradlew --version
~~~

Windows PowerShell:

~~~powershell
java -version
javac -version
.\gradlew.bat --version
~~~

`java -version` kiểm tra Java mà terminal thấy trên `PATH` (hoặc cấu hình liên quan). `./gradlew --version` xác nhận **Gradle runtime** thực sự được Wrapper khởi chạy, đồng thời hiển thị thông tin JVM/OS. Đừng giả định con số Gradle trong `gradle-wrapper.properties` đã được áp dụng nếu lệnh Wrapper đang lỗi.

**JDK và Gradle là hai phiên bản khác nhau.** Ví dụ dự án có thể biên dịch mã Java 21 bằng toolchain 21, trong khi JVM chạy Gradle có thể là JDK tương thích khác. Hãy kiểm tra ma trận tương thích giữa JDK chạy Gradle, Java toolchain và plugin Spring Boot của dự án.

### Bước 2 — Xem task và build

Linux/macOS:

~~~bash
./gradlew tasks
./gradlew clean test
./gradlew build
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat tasks
.\gradlew.bat clean test
.\gradlew.bat build
~~~

Giải thích:

- `tasks` liệt kê task do Gradle và các plugin đã áp dụng cung cấp.
- `clean` xóa đầu ra build do task `clean` quản lý trong project (thường `build/`); nó **không xóa** Gradle user home, Wrapper distribution hoặc toàn bộ dependency cache.
- `test` chạy test theo cấu hình build. Nếu test fail, quá trình build có thể báo `BUILD FAILED`; không nên bỏ qua để ép build xanh.
- `build` thường thực thi vòng đời build, bao gồm kiểm tra và tạo artifact theo cấu hình plugin; các task thực tế có thể khác giữa dự án.

Sau khi thành công, Gradle thường in dòng `BUILD SUCCESSFUL` nhưng số task, thời gian và các dòng log **không cố định**. Không xem việc đã hiện `BUILD SUCCESSFUL` của task `help` là bằng chứng rằng ứng dụng đã được test và chạy đúng.

### Bước 3 — Chạy Spring Boot qua bootRun

Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

`bootRun` chạy ứng dụng Spring Boot bằng cấu hình runtime của Gradle plugin. Với **Spring Web** và cấu hình mặc định, ứng dụng servlet thường lắng nghe HTTP trên cổng **8080**. Tuy nhiên, cổng thực tế có thể đã đổi qua `server.port` hoặc biến môi trường, và ứng dụng không có web starter sẽ không tự mở HTTP endpoint.

Một số thao tác thực tế:

- Để thử endpoint đã triển khai, mở terminal thứ hai và gọi đúng URL/cổng của project.
- Để dừng ứng dụng đang chạy tương tác trong terminal, dùng **Ctrl+C**.
- Nếu báo cổng bị chiếm, kiểm tra ứng dụng khác đang dùng cổng đó hoặc chỉnh `server.port` của project.
- Nếu báo thiếu main class hoặc nhiều main class, xem cấu hình class ứng dụng và `bootRun`/Spring Boot plugin; không coi đây là lỗi script Wrapper.

### Bước 4 — Đóng gói ứng dụng

Linux/macOS:

~~~bash
./gradlew bootJar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootJar
~~~

Khi task hoàn tất, executable Spring Boot JAR thường nằm tại `build/libs/`. Tên cụ thể phụ thuộc `archiveBaseName`, `archiveVersion` và các cấu hình khác. Spring Boot Gradle plugin có thể tạo cả **plain JAR** và **executable Boot JAR**, ví dụ tệp có hậu tố `-plain.jar` thường là JAR thông thường. Khi chạy ứng dụng hãy chọn đúng **Boot JAR có executable manifest/launcher**, không đoán từ thứ tự tệp trong thư mục.

Với một artifact thực sự tên `my-spring-app-1.0.0.jar`, lệnh chạy minh họa:

~~~bash
java -jar build/libs/my-spring-app-1.0.0.jar
~~~

Lệnh này chỉ chạy khi tệp đúng tên đã được tạo. Nếu tên version khác, hãy dùng **tên JAR thật** trong `build/libs/`. `bootRun` và `java -jar` là hai cách chạy khác nhau: cách thứ nhất chạy thông qua Gradle task, cách thứ hai chạy artifact đã đóng gói, nên có thể khác classpath/argument nếu project cấu hình đặc biệt.

## 6. Wrapper lấy phiên bản Gradle ở đâu?

Mở tệp **`gradle/wrapper/gradle-wrapper.properties`**. Một cấu hình minh họa:

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

**Các giá trị trên chỉ là ví dụ**; file thực tế của dự án có thể dùng phiên bản và tùy chọn khác. Mục quan trọng nhất:

- **`distributionUrl`** trỏ đến ZIP của bản Gradle sẽ chạy. Phần tên `gradle-9.9.0-bin.zip` ở ví dụ biểu thị **Gradle 9.9.0**, không liên quan trực tiếp đến Java 9 hoặc Spring Boot 9.
- **`-bin`** là distribution dành cho runtime Gradle, thường tải gọn hơn.
- **`-all`** còn gồm sources/docs phục vụ phát triển và trải nghiệm IDE; không bắt buộc cho việc build cơ bản.
- **`distributionBase`, `distributionPath`, `zipStoreBase`, `zipStorePath`** điều khiển nơi Wrapper lưu distribution/ZIP.
- Một số dự án cấu hình thêm `distributionSha256Sum` để kiểm tra checksum ZIP, thời gian chờ mạng hoặc cơ chế proxy riêng.

Khi chưa có distribution tương ứng, Wrapper cần tải nó, giải nén rồi chạy Gradle. Các lần sau có thể dùng bản đã lưu trong cache. Vì vậy **lần chạy đầu cần kết nối mạng** nếu môi trường chưa có distribution (và có thể còn cần mạng để tải project dependencies); chạy offline chỉ thành công khi tất cả tài nguyên cần thiết đã có.

Wrapper **không tự cài JDK**. Một số môi trường có cơ chế Gradle Java toolchain provisioning nếu đã được cấu hình thích hợp, nhưng điều đó là tính năng/cấu hình toolchain của Gradle, không phải chức năng mặc định của Wrapper.

## 7. Giữ dự án và CI nhất quán

Trong nhóm phát triển, hãy commit cả bốn tệp Wrapper cùng tệp build. Khi đồng đội clone project, họ chạy lệnh Wrapper của project thay vì tự chọn phiên bản Gradle toàn cục. CI cũng nên sử dụng Wrapper để giảm chênh lệch môi trường.

Ví dụ bước build cơ bản trên một runner Linux đã có JDK phù hợp:

~~~bash
java -version
./gradlew --version
./gradlew --no-daemon clean test
./gradlew --no-daemon bootJar
~~~

`--no-daemon` yêu cầu không dùng một Gradle Daemon lâu dài cho invocation đó theo cơ chế Gradle; việc tạo JVM chuyên biệt vẫn có thể xảy ra tùy tùy chọn JVM. Cờ này thường được cân nhắc trong CI nhưng không phải quy tắc bắt buộc: dựa trên chiến lược cache, memory và runner của team.

Tương đương khi CI dùng Windows PowerShell:

~~~powershell
java -version
.\gradlew.bat --version
.\gradlew.bat --no-daemon clean test
.\gradlew.bat --no-daemon bootJar
~~~

**Điều kiện để tái lập build** không dừng ở Wrapper: CI còn cần JDK phù hợp, dependency repositories có thể truy cập, version plugin/dependency được quản lý có kiểm soát, biến môi trường cần thiết và cấu hình test. Nếu dùng dependency động hoặc repository thay đổi, cùng Gradle version vẫn có thể cho kết quả khác.

Trên Linux/macOS, file `gradlew` trong Git cần được lưu với executable bit. Nếu file chỉ chạy được sau khi `chmod +x gradlew` thủ công trên từng máy, hãy sửa quyền được Git theo dõi tại repository và commit thay đổi đó.

## 8. Nâng cấp phiên bản Gradle Wrapper an toàn

Nâng cấp Gradle có thể ảnh hưởng build scripts, plugins, JDK chạy Gradle và CI. **Trước khi nâng cấp**, kiểm tra:

1. Phiên bản **Spring Boot Gradle plugin** mà project dùng hỗ trợ Gradle mục tiêu hay chưa.
2. JDK chạy Gradle và Java toolchain có nằm trong ma trận tương thích Gradle mục tiêu hay không.
3. Plugin bên thứ ba và cú pháp Gradle DSL (Groovy/Kotlin) có cần thay đổi không.
4. Team/CI có yêu cầu cố định dòng Gradle cụ thể không.

**Ví dụ có chủ đích:** Giả sử đã xác nhận Gradle **9.9.0** phù hợp với project của bạn, trên Linux/macOS chạy tại root:

~~~bash
./gradlew :wrapper --gradle-version 9.9.0 --distribution-type bin
./gradlew :wrapper --gradle-version 9.9.0 --distribution-type bin
./gradlew --version
./gradlew clean test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat :wrapper --gradle-version 9.9.0 --distribution-type bin
.\gradlew.bat :wrapper --gradle-version 9.9.0 --distribution-type bin
.\gradlew.bat --version
.\gradlew.bat clean test
~~~

**Tại sao chạy `:wrapper` hai lần?** Theo hướng dẫn Gradle, lần đầu thường cập nhật `gradle-wrapper.properties`; lần chạy tiếp theo giúp làm mới cả `gradle-wrapper.jar` và các script theo phiên bản Gradle mới (nếu chúng cần thay đổi). Dùng `:wrapper` để nhắm task ở root của multi-project build. Lần chạy đầu có thể cần tải Gradle mới ở lần chạy tiếp theo; cần mạng nếu distribution chưa được cache.

Sau nâng cấp, review thay đổi trong `gradlew`, `gradlew.bat`, `gradle-wrapper.jar` và `gradle-wrapper.properties`, chạy bộ test/build phù hợp rồi commit cả nhóm tệp đã thay đổi. Nếu lỗi tương thích, phân tích thông báo lỗi và hướng dẫn nâng cấp Gradle/Spring Boot; không tiếp tục đổi ngẫu nhiên nhiều version.

**Không tự sửa nội dung script hay thay JAR bằng một file lấy từ nguồn không rõ.** Có thể chỉnh `distributionUrl` thủ công trong các tình huống có kiểm soát, nhưng cách ưu tiên là chạy task `wrapper` để đồng bộ các tệp sinh ra.

## 9. Kiểm tra tính toàn vẹn và nguồn tải của Wrapper

Wrapper tải và chạy mã build, vì vậy tệp bootstrap cùng URL distribution phải đáng tin.

- **URL:** Ưu tiên distribution chính thức từ `https://services.gradle.org/distributions/` hoặc mirror do tổ chức quản lý. Review thay đổi `distributionUrl` trong pull request.
- **Checksum distribution:** Có thể cấu hình `distributionSha256Sum` bằng SHA-256 **chính thức của đúng ZIP và đúng phiên bản** để kiểm tra nội dung khi tải về. Không chép checksum của phiên bản khác. Việc kiểm tra này là cho **ZIP Gradle**, khác với xác thực file `gradle-wrapper.jar`.
- **Wrapper JAR:** Có thể kiểm tra checksum của `gradle/wrapper/gradle-wrapper.jar` theo danh sách checksum được Gradle công bố: https://gradle.org/release-checksums/ . Một số hệ thống CI có action hỗ trợ xác thực Wrapper JAR.
- **Không tùy tiện dùng cờ bỏ qua xác thực**, thay distribution bằng HTTP không tin cậy, hoặc tải JAR ngẫu nhiên từ website khác.

Ví dụ tính SHA-256 file Wrapper JAR trên Linux/macOS (công cụ `sha256sum` có thể không được cài sẵn trên mọi macOS; có thể dùng `shasum -a 256`):

~~~bash
shasum -a 256 gradle/wrapper/gradle-wrapper.jar
~~~

Trên Windows PowerShell:

~~~powershell
(Get-FileHash .\gradle\wrapper\gradle-wrapper.jar -Algorithm SHA256).Hash
~~~

Sau khi có hash, đối chiếu với checksum chính thức của **Wrapper JAR**. Lệnh chỉ in hash, không tự kết luận file an toàn. Xác thực checksum là bước đặc biệt có ích khi review nâng cấp, nguồn code không quen thuộc hoặc pipeline cần kiểm tra nguồn tin cậy.

## 10. Lỗi thường gặp khi dùng gradlew/gradlew.bat

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `./gradlew: No such file or directory` | Chạy sai thư mục hoặc project không có Wrapper | Mở root chứa `gradlew`; kiểm tra dự án có phải Gradle và có bốn tệp Wrapper không |
| PowerShell báo `gradlew.bat is not recognized` | Thiếu `.\` hoặc chạy sai thư mục | Dùng `.\gradlew.bat tasks` tại root |
| `Permission denied` với `./gradlew` | File script thiếu quyền execute | Chạy `chmod +x gradlew`, đồng thời ghi nhận executable bit trong Git |
| `Could not find or load main class org.gradle.wrapper.GradleWrapperMain` | Thiếu/hỏng `gradle-wrapper.jar` hoặc cấu trúc Wrapper không đầy đủ | Khôi phục đủ tệp Wrapper từ repository đáng tin; không tải JAR tùy tiện |
| `JAVA_HOME is set to an invalid directory` | `JAVA_HOME` trỏ sai hoặc JDK bị di chuyển | Đặt `JAVA_HOME` vào thư mục JDK hợp lệ, kiểm tra `java -version` |
| `Unsupported class file major version` hoặc thông báo JDK không được hỗ trợ | Gradle/plugin và JVM/JDK đang dùng không tương thích | Xem `--version`, JDK của IDE/CI, bảng tương thích Java–Gradle–Spring Boot |
| Download lỗi timeout, 403, SSL/PKIX | Mạng/proxy/chứng chỉ/mirror bị lỗi hoặc bị chặn | Kiểm tra URL, proxy, SSL trust store, kết nối và repo được cấu hình |
| `Task 'bootRun' not found` | Project không áp dụng Spring Boot Gradle plugin hoặc chọn sai build/root | Chạy `tasks`; kiểm tra `build.gradle(.kts)` và module chứa Spring Boot app |
| `Task 'build' not found` hoặc không tìm thấy build | Chạy sai project hoặc cấu hình plugin/build scripts chưa đúng | Xem `settings.gradle(.kts)` và `tasks --all`, thông báo lỗi cấu hình thực tế |
| Chạy `--offline` nhưng báo thiếu module/distribution | Một số dependencies hoặc bản Gradle chưa được tải | Chạy online để tải đầy đủ trước; `--offline` không thay thế cache bị thiếu |
| Wrapper được nâng cấp nhưng script/JAR chưa đổi | Mới chạy `wrapper` một lần | Chạy task `:wrapper` lần hai với phiên bản đã duyệt, kiểm tra diff |
| Build chạy được local nhưng fail trên CI | JDK, quyền script, biến môi trường hoặc dependency access khác | Đối chiếu `java -version`, `./gradlew --version`, executable bit và log CI |

### Cách khoanh vùng lỗi có hệ thống

**Bước A — Kiểm tra lệnh đã gọi:** Xác nhận đang ở root, chọn đúng `./gradlew` hoặc `.\gradlew.bat`; kiểm tra file Wrapper tồn tại.

**Bước B — Kiểm tra bootstrap:** Gọi `--version`. Nếu lệnh này thất bại, xử lý trước vấn đề JDK, quyền execute, tệp Wrapper hoặc tải distribution. Chưa cần suy đoán lỗi code Spring Boot.

**Bước C — Kiểm tra Gradle build:** Sau khi `--version` hoạt động, gọi `tasks` rồi `test`. Nếu fail ở bước cấu hình, tập trung vào plugin, repositories, dependencies và JVM.

**Bước D — Kiểm tra Spring Boot:** Khi Gradle đã chạy, gọi `bootRun` hoặc `bootJar`. Nếu lỗi startup/HTTP, tập trung vào cấu hình ứng dụng, dependency, cổng và code Spring Boot; Wrapper lúc này thường đã hoàn tất vai trò của nó.

Đọc lỗi gốc trong stack trace/log; cờ `--stacktrace` có thể giúp tìm nguyên nhân lỗi task, `--info` hoặc `--debug` cung cấp thêm log nếu cần. Không mặc định xóa toàn bộ Gradle cache: cách này buộc tải lại dữ liệu, có thể làm lỗi mạng nặng hơn và không giải quyết vấn đề tương thích.

## 11. Câu hỏi tự luyện và checklist

**Tình huống 1:** Một dự án có `gradlew` nhưng máy chưa cài Gradle. Có chạy `./gradlew test` được không?

Có, nếu project có đủ tệp Wrapper, JDK tương thích và có bản Gradle đã cache hoặc tải được qua `distributionUrl`. Không cần cài Gradle toàn cục.

**Tình huống 2:** Máy Windows có PowerShell, người học chạy `gradlew.bat build` và nhận lỗi không nhận diện lệnh. Cần thử gì trước?

Kiểm tra đang ở root, sau đó gọi `.\gradlew.bat build`. Đây là cú pháp gọi chương trình trong thư mục hiện hành của PowerShell.

**Tình huống 3:** Team đổi `distributionUrl` sang bản Gradle mới; Java source không đổi nhưng CI fail ngay khi cấu hình build. Vì sao?

Vì version Gradle mới có thể không tương thích JDK chạy Gradle, Spring Boot plugin, plugin khác hoặc build DSL hiện tại. Cần xem log và ma trận tương thích thay vì chỉ kiểm tra Java source.

**Tình huống 4:** Khi nào dùng `./gradlew bootJar` và khi nào dùng `./gradlew bootRun`?

`bootRun` dùng để chạy ứng dụng trực tiếp qua Gradle phục vụ phát triển/kiểm tra; `bootJar` tạo executable Boot JAR để chạy hoặc phân phối sau đó. Cả hai yêu cầu Spring Boot Gradle plugin.

**Tự kiểm tra:**

- [ ] Xác định đúng bốn tệp Wrapper trong project, hiểu chức năng của từng tệp.
- [ ] Phân biệt `gradle` toàn cục với `gradlew`/`gradlew.bat` theo phiên bản dự án.
- [ ] Chạy được `--version`, `tasks`, `test` và `build` bằng cú pháp đúng hệ điều hành.
- [ ] Chạy được `bootRun` hoặc `bootJar` khi project áp dụng Spring Boot Gradle plugin.
- [ ] Giải thích được `distributionUrl`, cache distribution và quan hệ với JDK.
- [ ] Biết quy trình nâng cấp Wrapper qua task `:wrapper`, kiểm tra tương thích và review diff.
- [ ] Biết xử lý lỗi sai đường dẫn, thiếu executable bit, JDK, file JAR, mạng và task không tồn tại.

## Tài liệu chính thức

- Gradle Wrapper — cách dùng, cấu trúc, nâng cấp, xác thực: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Gradle Wrapper Basics: https://docs.gradle.org/current/userguide/gradle_wrapper_basics.html
- Gradle Java compatibility: https://docs.gradle.org/current/userguide/compatibility.html
- Gradle release checksums: https://gradle.org/release-checksums/
- Spring Boot Gradle Plugin: https://docs.spring.io/spring-boot/gradle-plugin/index.html
- Spring Boot system requirements (kiểm tra theo phiên bản đang dùng): https://docs.spring.io/spring-boot/system-requirements.html

**Kết quả bài học:** Bạn có thể checkout một dự án Spring Boot Gradle trên Linux, macOS hoặc Windows và dùng đúng Wrapper của dự án để xem phiên bản, build, test, chạy ứng dụng, đóng gói và chẩn đoán các lỗi môi trường phổ biến.