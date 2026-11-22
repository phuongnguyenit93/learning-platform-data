# Build chạy được trong IDE nhưng lỗi ở terminal hoặc CI

Một build chạy thành công trong IDE nhưng thất bại khi chạy từ terminal hoặc CI thường cho thấy hai môi trường đang thực hiện build với cấu hình hoặc điều kiện khác nhau. Source code có thể giống nhau, nhưng JVM, Gradle version, task được gọi, biến môi trường, working directory, dependency cache, quyền truy cập file và hệ điều hành có thể khác.

Điều quan trọng đầu tiên là xác định IDE đang thực hiện **Gradle build thật** hay chỉ dùng compiler/build system riêng của IDE. Một lần IDE báo Build Successful chưa chắc tương đương với lệnh `./gradlew clean build`. IDE có thể chỉ compile module đang mở, chạy một test class, bỏ qua integration test hoặc dùng compiler nội bộ.

Muốn tìm nguyên nhân, hãy tái hiện đúng task và cấu hình mà IDE đang chạy, sau đó so sánh từng lớp môi trường với terminal/CI. Đừng vội sửa source hoặc thêm dependency trước khi biết hai lần build thực sự khác nhau ở đâu.

## 1. Hiểu đúng “build chạy được trong IDE”

IDE Java thường tích hợp nhiều chức năng: editor, compiler, test runner, debugger, Gradle/Maven integration và cấu hình chạy ứng dụng. Những chức năng này có thể dùng các runtime hoặc cách thực thi khác nhau.

Ví dụ với IntelliJ IDEA:

- Build Project có thể dùng IntelliJ compiler nếu build actions chưa được delegate sang Gradle.
- Gradle tool window có thể chạy task bằng Gradle Wrapper.
- Run/Debug configuration có thể dùng module classpath do IDE quản lý.
- Gradle sync chỉ cấu hình/import project; nó không nhất thiết chạy toàn bộ test hoặc task build.
- Test runner có thể chạy test bằng IDE runner hoặc Gradle test task.

Với Eclipse hoặc IDE khác, tên và cách cấu hình khác nhau, nhưng nguyên tắc tương tự: cần biết build action nào đã chạy và công cụ nào thực hiện nó.

### 1.1. Phân biệt IDE compiler với Gradle build

Một project có thể có hai đường build:

~~~text
                    Source code
                         |
             +-----------+-----------+
             |                       |
             v                       v
      IDE build system          Gradle Wrapper
             |                       |
      IDE compiler/model       Gradle task graph
             |                       |
       IDE output folder       Gradle build/tasks
             |                       |
      IDE test runner          Gradle test task
             |                       |
             +-----------+-----------+
                         |
                  Runtime/application
~~~

Hai đường này có thể cùng tạo class files nhưng không nhất thiết dùng cùng:

- Compiler và compiler options.
- Annotation processors.
- Generated source directories.
- Dependency resolution.
- Test framework/runner.
- Java SDK hoặc toolchain.
- Resource filtering và task ordering.

Vì vậy, IDE compile pass không chứng minh Gradle build pass. Ngược lại, Gradle build pass cũng không bảo đảm IDE đang dùng đúng project model để chạy/debug.

### 1.2. Xác nhận IDE có delegate build sang Gradle không

Nếu project dùng Gradle, kiểm tra cài đặt build/run của IDE để biết build actions được thực thi bởi Gradle hay IDE compiler. Với IntelliJ IDEA, có thể chọn delegate build and run actions to Gradle và chọn Gradle JVM riêng.

Nếu IDE dùng Gradle, mở Gradle tool window và chạy chính task đang lỗi ở terminal. Nếu IDE dùng compiler nội bộ, hãy chạy Gradle Wrapper từ terminal để kiểm tra build thật.

| Thao tác | Điều nó chứng minh |
|---|---|
| IDE Gradle sync thành công | Gradle có thể cấu hình/import build trong môi trường IDE |
| IDE Build Project thành công | Build system được IDE chọn đã compile phần được yêu cầu |
| IDE chạy một test thành công | Test runner và classpath của lần chạy đó hoạt động |
| `./gradlew build` thành công | Gradle lifecycle task được gọi đã hoàn thành trong môi trường terminal |
| CI pipeline thành công | Build thành công trong môi trường runner và các bước pipeline đã cấu hình |

Hãy so sánh cùng một task, không so sánh IDE Build Project với CI clean build rồi kết luận rằng CI bị lỗi ngẫu nhiên.

## 2. JVM và JDK được chọn khác nhau

Đây là nguyên nhân phổ biến nhất. Một máy có thể cài nhiều JDK và mỗi công cụ có thể chọn một bản khác.

Các lớp Java cần phân biệt:

1. **IDE runtime:** JVM chạy chính ứng dụng IDE.
2. **Gradle JVM/daemon:** JVM chạy Gradle và nạp plugin/build logic.
3. **Java toolchain:** JDK dùng để compile và có thể chạy test.
4. **Test launcher:** JVM thực thi test worker.
5. **Application runtime:** JVM chạy ứng dụng.
6. **CI runtime:** JDK được runner hoặc container dùng để chạy Gradle.
7. **Production runtime:** JDK/JRE trên server hoặc container triển khai.

IDE có thể chạy bằng JDK 21, Gradle JVM cũng được cấu hình là JDK 21, trong khi terminal lấy JAVA_HOME là JDK 17. Hoặc IDE dùng JDK 17 cho Gradle nhưng toolchain compile là JDK 21. CI lại dùng JDK 11. Cùng một source tree vì vậy có thể cho kết quả khác nhau.

### 2.1. Thu thập Java version từ đúng môi trường

Trong terminal, chạy:

~~~bash
java -version
javac -version
~~~

Trên Windows PowerShell:

~~~powershell
java -version
javac -version
Get-Command java
Get-Command javac
$env:JAVA_HOME
~~~

Sau đó chạy Gradle Wrapper của project:

~~~bash
./gradlew --version
~~~

Trên Windows:

~~~powershell
.\gradlew.bat --version
~~~

Đọc phần JVM/Java home trong output của Gradle. Đừng chỉ dựa vào java -version: Gradle daemon có thể dùng JVM khác với lệnh java trong PATH.

Nếu Java plugin được áp dụng, có thể xem các JDK mà Gradle phát hiện:

~~~bash
./gradlew javaToolchains
~~~

Trong IDE, kiểm tra Gradle JVM setting và Project SDK/Project Structure. Hai cài đặt này có thể khác nhau.

### 2.2. Java toolchain không phải Gradle JVM

Ví dụ build dùng JDK 21 để compile nhưng Gradle daemon chạy bằng JDK 17:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Đây có thể là cấu hình hợp lệ nếu Gradle version và plugin hỗ trợ JVM 17, đồng thời toolchain JDK 21 có sẵn. Toolchain chọn compiler/test launcher theo cấu hình task; nó không tự đổi JVM chạy Gradle daemon.

Nếu plugin cần Java 21 nhưng daemon chỉ chạy Java 17, build có thể lỗi ngay ở giai đoạn configuration trước khi task compile được thực thi.

### 2.3. Chuẩn hóa toolchain và Java release

Nên ghi rõ JDK dùng cho Java task trong build script:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Toolchain chọn JDK compiler. `options.release` giới hạn source language, bytecode target và Java platform API ở release 17. Cách này giúp tránh việc developer compile bằng JDK mới hơn rồi vô tình sử dụng API không có trên runtime mục tiêu.

Nếu project có Kotlin, Scala hoặc compiler plugin khác, cần cấu hình JVM target tương ứng. Java toolchain không tự động bảo đảm mọi language compiler tạo bytecode cùng baseline.

### 2.4. Gradle version cũng phải tương thích với JDK

Gradle Wrapper khóa phiên bản Gradle distribution, nhưng JDK chạy Gradle vẫn được chọn từ môi trường hoặc cấu hình. Một Gradle release cũ có thể không hỗ trợ chạy trên JDK mới, hoặc plugin mới yêu cầu Gradle API/JDK mới hơn.

Kiểm tra ba yếu tố cùng lúc:

- Gradle distribution trong `gradle/wrapper/gradle-wrapper.properties`.
- JVM chạy Gradle trong terminal/IDE/CI.
- Phiên bản plugin và JDK tối thiểu plugin yêu cầu.

Không nên chỉ nâng JDK trên CI mà giữ nguyên wrapper và plugin mà chưa kiểm tra compatibility.

## 3. Terminal đang dùng Gradle khác với IDE

Project có thể chạy Gradle Wrapper trong IDE nhưng dùng lệnh gradle cài global ở terminal. Hai lệnh có thể chạy hai Gradle version khác nhau.

### 3.1. Luôn xác định lệnh Gradle được gọi

Trong project có Wrapper, dùng:

~~~bash
./gradlew build
~~~

Trên Windows:

~~~powershell
.\gradlew.bat build
~~~

Lệnh gradle build sử dụng Gradle được cài và tìm thấy qua PATH. Nó có thể không giống Gradle version được khóa trong Wrapper.

Kiểm tra:

~~~bash
gradle --version
./gradlew --version
~~~

Nếu hai output khác nhau, hãy dùng Wrapper để tái hiện môi trường mà project mong đợi.

### 3.2. Kiểm tra Wrapper và distribution URL

Wrapper configuration nằm trong:

~~~text
gradle/
└── wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Ví dụ:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
~~~

`distributionUrl` xác định Gradle distribution mà Wrapper tải và chạy. Nếu file này thay đổi giữa local và CI, hai môi trường có thể chạy Gradle version khác nhau.

Wrapper JAR và properties nên được quản lý trong source control. Nếu CI dùng cache wrapper, vẫn cần xác nhận distribution được tải đúng version và integrity policy của tổ chức.

### 3.3. Dừng daemon cũ khi cần kiểm tra

Gradle daemon được tái sử dụng để giảm thời gian khởi động. Khi đổi JDK, JVM arguments hoặc môi trường, daemon mới có thể được tạo; daemon cũ vẫn có thể tồn tại cho tới khi dừng.

Có thể yêu cầu Gradle dừng daemon:

~~~bash
./gradlew --stop
~~~

Sau đó chạy lại đúng lệnh build và xem `./gradlew --version`. Lệnh này hữu ích để loại trừ daemon cũ trong quá trình chẩn đoán. Nó không sửa một JAVA_HOME, toolchain hoặc plugin configuration vốn sai.

Không cần dừng daemon sau mỗi lần build. Chỉ dùng khi đang điều tra khác biệt JVM hoặc trạng thái daemon.

## 4. Task được IDE chạy khác task trong terminal/CI

Một trong những nguyên nhân dễ bị bỏ sót là hai bên không chạy cùng task.

Ví dụ:

- IDE compile source nhưng không chạy test.
- IDE chạy một test class, CI chạy toàn bộ test suite.
- Terminal chạy build, kéo theo check/test và các task lifecycle khác.
- CI chạy clean build publish, thêm task integration hoặc packaging.
- IDE chỉ build một subproject, CI build từ root.
- CI có task kiểm tra format, static analysis hoặc generated source mà IDE không chạy.

### 4.1. Xác định task graph thực tế

Chạy task cụ thể với thông tin chi tiết:

~~~bash
./gradlew build --info --stacktrace
~~~

Nếu lỗi ở task khác, chạy đúng task đó:

~~~bash
./gradlew :orders-service:test --info --stacktrace
~~~

Có thể xem task có trong build:

~~~bash
./gradlew tasks
~~~

Không nên dùng tasks để thay thế việc chạy task đang thất bại; nó chỉ giúp xác định task và cấu trúc build.

### 4.2. So sánh cùng một lệnh ở IDE và terminal

Trong Gradle tool window của IDE, chạy task đúng tên và xem command/task output. Sau đó chạy cùng task bằng Wrapper từ root project.

Ví dụ:

~~~bash
./gradlew :orders-service:check
~~~

Nếu IDE dùng Gradle và task này pass, nhưng terminal chạy ./gradlew build fail, hãy xem các task được gọi thêm bởi lifecycle build. Có thể lỗi nằm ở test, checkstyle, integration test, packaging hoặc task custom chứ không nằm ở compile.

### 4.3. Gradle sync không phải build đầy đủ

Sync/import project thường resolve plugin, đọc settings và cấu hình project model. Nó có thể không thực thi các task compile/test/verification.

Một project có thể sync thành công nhưng compile thất bại vì thiếu toolchain, generated sources hoặc dependency chỉ được resolve khi task chạy. Ngược lại, sync có thể fail vì IDE không truy cập được repository/plugin portal dù một terminal đã có cache.

Hãy ghi rõ thao tác IDE nào thành công: Sync, Build Project, Run, Debug hay Gradle task. Tên “build thành công” quá chung để chẩn đoán.

## 5. Working directory và project root khác nhau

Gradle có thể cho kết quả khác khi được gọi từ thư mục khác. Điều này đặc biệt quan trọng với multi-project build, composite build và script dùng relative path.

Ví dụ repository:

~~~text
commerce/
├── settings.gradle
├── build.gradle
├── services/
│   ├── orders/
│   │   └── build.gradle
│   └── payments/
│       └── build.gradle
└── libraries/
    └── common/
        └── build.gradle
~~~

IDE có thể mở root commerce/, nhưng terminal đang ở services/orders/. Nếu chạy lệnh từ thư mục không mong đợi, Gradle có thể chọn build root khác hoặc project context khác.

### 5.1. Chỉ định project directory rõ ràng

Có thể dùng -p hoặc --project-dir:

~~~bash
./gradlew -p /workspace/commerce :services:orders:build
~~~

Trên Windows:

~~~powershell
.\gradlew.bat -p C:\workspace\commerce :services:orders:build
~~~

Dùng path tuyệt đối trong ví dụ để loại bỏ sự mơ hồ về working directory. Trong CI, cấu hình working directory của job/step cần trỏ tới đúng root.

### 5.2. Relative paths trong build script

Các path tương đối có thể được resolve theo project directory, settings directory hoặc thư mục làm việc tùy API đang sử dụng. Script tự gọi shell command hoặc đọc file bằng relative path càng dễ phụ thuộc current working directory.

Với task, nên dùng Gradle file properties/provider gắn với project hoặc task thay vì dựa vào process current directory. Ví dụ dùng `layout.projectDirectory.file(...)` để tham chiếu file thuộc project.

~~~groovy
tasks.register('copyConfig') {
    def configFile = layout.projectDirectory.file('config/app.yml')
    inputs.file(configFile)
    // Task action sử dụng configFile đã khai báo
}
~~~

Điều này giúp đường dẫn có ý nghĩa rõ ràng và dễ tái sử dụng trong build khác.

### 5.3. Multi-project và composite build

Với multi-project build, IDE có thể import root project trong khi terminal vô tình chạy Wrapper từ một thư mục con có settings riêng.

Với composite build, `includeBuild('../shared-library')` được tính theo vị trí settings script chứa khai báo. Nếu checkout CI có cấu trúc thư mục khác với workspace IDE, included build có thể không tồn tại.

Hãy kiểm tra đường dẫn và nội dung checkout thực tế trong CI, đặc biệt khi dùng submodule, sparse checkout hoặc checkout nhiều repository vào các thư mục khác nhau.

## 6. Biến môi trường và cấu hình máy khác nhau

IDE thường kế thừa environment từ lúc IDE được khởi chạy, còn terminal kế thừa environment từ shell hiện tại. CI lại dùng environment do runner/pipeline định nghĩa.

Các biến có thể ảnh hưởng build:

- JAVA_HOME, PATH.
- GRADLE_USER_HOME.
- HTTP_PROXY, HTTPS_PROXY, NO_PROXY.
- Biến chọn profile/configuration.
- Token truy cập artifact repository.
- Biến chỉ môi trường dev/test/prod.
- Locale, timezone hoặc encoding.
- Biến được task custom đọc trong action.

### 6.1. IDE có thể không nhận biến môi trường mới

Nếu thay đổi JAVA_HOME trong shell sau khi IDE đã mở, IDE đang chạy có thể vẫn giữ environment cũ. Tương tự, terminal tích hợp bên trong IDE có thể khởi tạo shell với environment khác terminal bên ngoài.

Khi nghi ngờ, so sánh environment trong đúng process chạy Gradle. Đóng/mở lại IDE có thể cần thiết sau khi đổi biến môi trường hệ thống, nhưng trước tiên hãy xác nhận giá trị thực tế để tránh thay đổi không cần thiết.

### 6.2. Không in toàn bộ environment trong CI

Environment có thể chứa token, password, signing key hoặc credential. Không nên dùng env, printenv hay dump toàn bộ biến vào log CI.

Chỉ in các giá trị không nhạy cảm cần chẩn đoán, ví dụ:

~~~bash
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
printf 'GRADLE_USER_HOME=%s\n' "$GRADLE_USER_HOME"
java -version
./gradlew --version
~~~

Nếu cần xác nhận credential có được cung cấp, chỉ kiểm tra biến có tồn tại hoặc kiểm tra quyền truy cập mà không in giá trị bí mật.

### 6.3. Cấu hình externalized và file .env

Một IDE run configuration có thể tự nạp file .env hoặc định nghĩa environment variables thủ công. Terminal và CI không tự động nạp các giá trị đó nếu script không cấu hình.

Nếu ứng dụng đọc APP_PROFILE, DATABASE_URL hoặc biến tương tự, hãy ghi rõ cách cung cấp trong README/pipeline. Không nên dựa vào biến chỉ tồn tại trên máy một developer.

### 6.4. Gradle properties và init scripts

Gradle có thể đọc cấu hình từ nhiều nơi:

- gradle.properties trong project.
- gradle.properties trong Gradle User Home.
- System properties và command-line options.
- Gradle init scripts trong Gradle User Home hoặc thư mục init script.
- Settings/build scripts và plugin management.

IDE có thể dùng Gradle User Home khác terminal hoặc cấu hình JVM/options khác. CI thường dùng home directory mới hoặc một Gradle User Home được cache riêng.

Điều này có thể làm thay đổi repository, proxy, credentials, plugin resolution, daemon JVM, parallelism hoặc build cache settings.

Khi so sánh, ghi nhận các file cấu hình liên quan và nguồn của chúng. Không copy toàn bộ ~/.gradle hoặc init script từ máy developer sang CI một cách mù quáng; chúng có thể chứa cấu hình cá nhân hoặc credential.

## 7. Dependency và plugin resolution khác nhau

IDE có thể build thành công vì dependency đã được tải và cache từ trước. Terminal hoặc CI dùng Gradle User Home mới nên phải resolve lại từ repository. Nếu repository bị chặn, credential thiếu hoặc artifact đã bị xóa, build có thể fail.

### 7.1. Kiểm tra dependency graph

Với dependency runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Để xem lý do Gradle chọn một version:

~~~bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Thay tên module/configuration theo project. Với plugin, cần kiểm tra plugin management và plugin repositories; dependency runtime của ứng dụng không đại diện cho plugin classpath.

### 7.2. Repository credentials và plugin repositories

Dependency có thể được resolve từ Maven Central, repository nội bộ hoặc plugin portal. IDE có thể có credential helper, proxy hoặc init script mà CI không có.

Kiểm tra:

- repositories trong project/settings.
- pluginManagement.repositories trong settings.
- Credential được cung cấp qua environment/secret store.
- Proxy/firewall và certificate trust.
- Repository URL có thể truy cập từ CI runner.
- Dependency version có thực sự tồn tại ở repository được cấu hình.

Không đưa token vào source control hoặc log. Dùng CI secret variables và cấu hình credential theo cơ chế Gradle phù hợp.

### 7.3. Cache dependency có thể che lỗi cấu hình

Một developer đã tải dependency từ trước có thể build offline hoặc qua cache, dù repository cấu hình hiện tại không còn truy cập được. CI agent mới không có cache đó nên lộ ra lỗi.

Có thể kiểm tra khả năng build khi không dùng cache dependency bằng cách dùng Gradle User Home sạch hoặc cache riêng cho job thử nghiệm. Làm việc này trong workspace tạm và không xóa Gradle cache cá nhân đang được dùng.

Tùy chọn --refresh-dependencies yêu cầu Gradle kiểm tra lại dependency theo cache policy; nó không phải cách sửa credential hoặc repository URL sai.

### 7.4. Plugin resolution xảy ra trước nhiều task

Nếu lỗi xảy ra trong settings/configuration hoặc ngay khi áp dụng plugin, hãy kiểm tra plugin version, plugin repositories và Gradle compatibility. Task compile chưa chạy nên thay dependency runtime của application có thể không liên quan.

## 8. Khác biệt hệ điều hành, filesystem và shell

Build chạy trên Windows nhưng fail trên Linux CI là tình huống thường gặp. Các khác biệt không chỉ nằm ở Java version.

### 8.1. Phân biệt chữ hoa/chữ thường trong đường dẫn

Windows filesystem thường không phân biệt hoa thường theo mặc định, trong khi Linux thường phân biệt.

Ví dụ source import hoặc resource tham chiếu:

~~~java
getResource("/Config/application.yml");
~~~

Nhưng file thật trong repository là:

~~~text
config/application.yml
~~~

Trên một máy Windows, đường dẫn có thể vẫn hoạt động; trên Linux, nó có thể không tìm thấy resource.

Kiểm tra chính tả, case của package, resource, thư mục và file được task tham chiếu. Git cũng có một số tình huống đổi tên chỉ khác chữ hoa/thường cần được xử lý cẩn thận trên filesystem không phân biệt case.

### 8.2. File permission và executable bit

CI Linux có thể chạy shell script cần executable permission. File có trên checkout nhưng không có executable bit có thể gây lỗi Permission denied.

Kiểm tra:

~~~bash
git ls-files --stage
ls -l ./gradlew
~~~

Gradle Wrapper trên Unix cần executable bit. Nếu bit bị mất trong Git, có thể khôi phục bằng git update-index --chmod=+x gradlew rồi commit thay đổi metadata file phù hợp.

Trên Windows, cách thực thi script và permission model khác Linux.

### 8.3. Path separator và path length

Windows dùng backslash trong native path, Unix-like dùng slash. Java thường hỗ trợ API path portable, nhưng script shell, command line và task custom có thể hard-code separator.

Windows cũng có giới hạn path phụ thuộc phiên bản và cấu hình. CI checkout ở path sâu có thể làm một số tool fail trong khi IDE project nằm ở đường dẫn ngắn hơn.

Dùng Gradle/Java path APIs và tránh ghép path bằng chuỗi thủ công. Nếu lỗi chỉ xuất hiện ở CI với path dài, kiểm tra đường dẫn workspace và output directories.

### 8.4. Line endings và file encoding

Git có thể checkout file với CRLF trên Windows và LF trên Linux. Script shell có thể fail nếu shebang hoặc line ending không đúng. Properties, YAML, SQL, template và source file cũng có thể bị ảnh hưởng bởi encoding.

Nên khai báo quy ước trong .gitattributes, ví dụ:

~~~gitattributes
*.sh text eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
*.java text
*.gradle text
*.gradle.kts text
~~~

Không phải mọi file đều nên bị ép cùng line ending. Chọn quy tắc phù hợp với loại file và tool sử dụng.

### 8.5. Default charset, locale và timezone

JDK, OS và environment có thể dùng default charset, locale hoặc timezone khác nhau. Điều này ảnh hưởng task đọc/ghi text nếu encoding không được chỉ định, format số/ngày, sort và test so sánh output.

Java 18 trở lên mặc định dùng UTF-8 cho nhiều API charset mặc định theo JEP 400, trong khi runtime cũ có thể phụ thuộc platform default. Nếu task cần UTF-8, hãy chỉ định encoding tường minh thay vì phụ thuộc default charset.

Nếu kết quả phụ thuộc timezone/locale, hãy cấu hình rõ hoặc đưa chúng thành input của task. Không để output cache thay đổi theo environment mà Gradle không biết.

### 8.6. Shell và quoting khác nhau

Một lệnh chạy trong Bash không nhất thiết chạy giống PowerShell hoặc cmd.exe. Cách quote chuỗi, biến môi trường, wildcard, dấu hai chấm trong project path và cách truyền argument có thể khác.

Ví dụ Bash:

~~~bash
./gradlew :orders-service:test --tests 'com.example.orders.OrderServiceTest'
~~~

PowerShell:

~~~powershell
.\gradlew.bat :orders-service:test --tests 'com.example.orders.OrderServiceTest'
~~~

Nếu script build tự gọi shell command, hãy xác định shell thực tế trong CI. Tránh phụ thuộc alias, function hoặc command chỉ có trên máy developer.

## 9. Generated sources và annotation processing

IDE có thể tự đánh dấu thư mục generated source hoặc tự chạy annotation processor theo project model. Terminal/CI chỉ tạo generated sources khi Gradle task/plugin được cấu hình đúng.

Các ví dụ thường gặp:

- Lombok hoặc annotation processor khác.
- MapStruct.
- OpenAPI/Swagger generator.
- Protobuf/gRPC code generation.
- Kotlin kapt hoặc KSP.
- Code generator nội bộ.

Nếu IDE build pass nhưng Gradle compile fail với cannot find symbol, hãy xem generated source có được tạo trước compile hay không.

### 9.1. Không dựa vào generated files còn sót trên máy

Một developer có thể đã chạy generator trước đó và IDE đang nhìn thấy output trong thư mục build. CI checkout sạch không có những file này.

Generated source nên là output của Gradle task và được nối vào source set/task graph đúng cách. Không nên yêu cầu developer commit output build tạm nếu project convention không quy định như vậy.

### 9.2. Khai báo task dependency rõ ràng

Gradle cần biết task compile sử dụng output của generator. Dùng task provider/output property để nối producer-consumer thay vì chỉ dựa vào thứ tự chạy thủ công.

Nếu generator tạo file nhưng không khai báo output, Gradle có thể không biết khi nào cần chạy lại hoặc khi nào output có thể được tái sử dụng.

## 10. Cache và Gradle daemon có thể làm hai môi trường khác nhau

IDE thường chạy build nhiều lần trên cùng workspace và Gradle User Home. CI có thể chạy trong workspace sạch hoặc dùng cache được restore từ job trước.

Các cơ chế liên quan:

- Up-to-date checking dựa trên output và execution history trong workspace.
- Build cache khôi phục output task theo cache key.
- Configuration cache tái sử dụng cấu hình/task graph.
- Dependency cache lưu metadata và artifact đã resolve.
- Gradle daemon tái sử dụng JVM process.

### 10.1. Thử build sạch để khoanh vùng

Trong workspace thử nghiệm, có thể chạy:

~~~bash
./gradlew clean build --no-build-cache --no-configuration-cache --stacktrace --info
~~~

Các flag --no-configuration-cache và một số cache options phụ thuộc Gradle version. Nếu wrapper cũ không nhận flag, bỏ flag không được hỗ trợ và ghi nhận khác biệt.

Lệnh này giúp loại trừ một số ảnh hưởng từ output hiện tại, build cache và configuration cache. Nó không xóa dependency cache, không đổi JVM và không sửa environment.

Chỉ chạy clean trong workspace dành cho build đó. Không chạy nhiều invocation đồng thời trên cùng build directory vì một task clean có thể xóa output của invocation khác.

### 10.2. So sánh khi bật lại cache

Nếu build sạch pass nhưng build thường fail, hãy bật lại từng cơ chế một:

1. Chạy lại với up-to-date checking bình thường.
2. Bật build cache.
3. Bật configuration cache nếu build hỗ trợ.
4. Dùng Gradle User Home/cache giống CI để so sánh dependency resolution.

Bật từng cơ chế giúp xác định phần nào làm thay đổi kết quả. Không nên xóa toàn bộ cache ngay từ đầu vì thao tác đó làm mất bằng chứng về cache entry hoặc dependency state đã gây ra khác biệt.

### 10.3. Remote build cache và CI

CI có thể đọc output từ remote cache được tạo bởi build khác. Chỉ task có inputs/outputs đầy đủ và cacheable mới nên dùng cache. Nếu custom task đọc environment hoặc file ẩn nhưng không khai báo input, cache hit có thể trả output không phù hợp.

Nếu nghi ngờ cache poisoning hoặc cache entry sai, kiểm tra quyền push và trust boundary của remote cache. Pull request không tin cậy thường chỉ nên đọc cache; pipeline tin cậy mới được ghi theo policy của tổ chức.

## 11. Cấu hình Gradle khác nhau giữa local và CI

Một build có thể bị ảnh hưởng bởi Gradle properties, init scripts, daemon settings và cấu hình project.

| Cấu hình | IDE/local | Terminal | CI |
|---|---|---|---|
| Gradle distribution | Có thể dùng Wrapper | Có thể vô tình dùng global Gradle | Thường nên dùng Wrapper |
| Gradle JVM | IDE Gradle JVM setting | JAVA_HOME/daemon criteria | Runner/container JDK |
| Toolchain | JDK được Gradle phát hiện/provision | Cùng build config nhưng có thể thiếu JDK | Runner cần provision/cài JDK |
| Gradle User Home | Home của user/IDE setting | Có thể khác shell | Home riêng của runner/cache |
| Init scripts | Có thể có script cá nhân | Có thể khác | Thường ít hơn hoặc được tổ chức quản lý |
| Credentials/proxy | IDE/helper có thể cung cấp | Shell environment | CI secrets/proxy |
| Working directory | Root project trong IDE | Thư mục terminal hiện tại | Working directory của job |
| Cache | Local/remote cache | Cache user | Cache restore/remote cache |
| OS/filesystem | Máy developer | Máy developer | Runner image/OS |

### 11.1. GRADLE_USER_HOME

Gradle User Home chứa nhiều dữ liệu và cấu hình theo user, bao gồm dependency cache, wrapper distributions, daemon state, init scripts và một số cấu hình global.

Có thể kiểm tra:

~~~bash
echo "$GRADLE_USER_HOME"
~~~

PowerShell:

~~~powershell
$env:GRADLE_USER_HOME
~~~

Nếu biến không được đặt, Gradle dùng vị trí mặc định trong user home. CI có thể đặt một thư mục khác hoặc cache nó giữa các job.

Khác Gradle User Home có thể giải thích tại sao IDE tìm thấy plugin/dependency nhưng CI không tìm thấy, hoặc vì sao hai bên dùng init script khác nhau.

### 11.2. Không sao chép cấu hình cá nhân sang repository

Một file ~/.gradle/init.gradle có thể cấu hình repository nội bộ hoặc plugin resolution trên máy developer. CI không có file đó nên build fail.

Giải pháp lâu dài là đưa cấu hình bắt buộc của project vào settings/build logic có kiểm soát, hoặc cung cấp init script chuẩn qua CI infrastructure. Credential vẫn phải lấy từ secret store.

### 11.3. Offline mode và dependency freshness

Nếu IDE chạy được khi offline do dependency đã cache nhưng CI cần tải dependency, build có thể fail vì repository/proxy. Ngược lại, local có thể resolve dynamic version khác CI do cache freshness khác nhau.

Dùng dependency locking và version cố định khi cần build tái lập. Với dynamic/changing dependencies, hiểu cache policy và kiểm soát thời điểm refresh.

## 12. CI runner, checkout và pipeline khác local

CI không chỉ là terminal ở một máy khác. Pipeline thường chạy trong môi trường tạm, có checkout riêng, user riêng, permission riêng và các bước trước/sau build.

### 12.1. Checkout không đầy đủ

CI có thể checkout source với shallow clone, sparse checkout hoặc không lấy Git submodules. Build script có thể đọc Git tags, commit history, submodule content hoặc file được tạo trong một bước pipeline trước đó.

Kiểm tra:

~~~bash
git status --short
git rev-parse --show-toplevel
git rev-parse HEAD
git submodule status
~~~

Nếu build dùng version từ Git tag/history, shallow checkout có thể làm version calculation thất bại hoặc tạo version khác local.

### 12.2. Build phụ thuộc file chưa được commit

Một file cấu hình, certificate test, generated source hoặc local properties có thể tồn tại trên máy developer nhưng không nằm trong repository. IDE dùng file đó và build pass; CI checkout sạch không có file.

Hãy xác định file có phải input chính thức của build không. Nếu có, quản lý file mẫu và cung cấp giá trị qua secret/config. Không commit credential hoặc private key để làm CI pass.

### 12.3. Runner image và package hệ thống

Một số task cần công cụ ngoài Java: Node, Python, Docker CLI, native compiler, database client, browser hoặc system library. IDE developer có thể có sẵn các tool này; CI runner image thì không.

Build script nên kiểm tra hoặc provision tool cần thiết một cách rõ ràng. Ghi lại version của tool ngoài nếu nó ảnh hưởng artifact.

### 12.4. Parallelism và resource limits

CI có thể chạy với số worker, CPU, memory và file descriptor khác local. Build chỉ fail khi chạy song song có thể do task custom có race condition, dùng output chung hoặc phụ thuộc thứ tự task không được khai báo.

Có thể thử chẩn đoán bằng:

~~~bash
./gradlew build --no-parallel --max-workers=1 --stacktrace --info
~~~

Nếu build pass khi tuần tự nhưng fail khi song song, điều tra shared mutable state, task output collision, generated files và external service. Không coi việc giảm worker là giải pháp cuối cùng nếu task vẫn có race.

CI memory limit thấp cũng có thể gây OOM hoặc process bị kill. Phân biệt lỗi resource với lỗi compile/dependency.

## 13. Quy trình chẩn đoán có thể lặp lại

Khi IDE pass nhưng terminal/CI fail, hãy đi theo thứ tự dưới đây. Mỗi bước cần thu thập bằng chứng trước khi đổi cấu hình.

### Bước 1: Ghi lại lệnh thành công và lệnh thất bại

Ghi chính xác:

- IDE action đã chạy (Sync, Build, Run, test hay Gradle task).
- Task Gradle cụ thể nếu có.
- Command terminal/CI đầy đủ.
- Working directory.
- Commit/source revision.
- Thời điểm và log lỗi đầu tiên.

Không chỉ ghi “IDE build pass” hoặc “CI fail”.

### Bước 2: Xác nhận source revision giống nhau

Kiểm tra commit, branch, uncommitted changes, submodules và generated files. CI phải build đúng commit mà bạn đang so sánh.

~~~bash
git rev-parse HEAD
git status --short
~~~

Một file chưa commit trên developer machine có thể là khác biệt duy nhất.

### Bước 3: Dùng Gradle Wrapper và cùng task

Chạy từ đúng root:

~~~bash
./gradlew :orders-service:build --stacktrace --info
~~~

Trên Windows:

~~~powershell
.\gradlew.bat :orders-service:build --stacktrace --info
~~~

Nếu IDE đang chạy task khác, đổi phép so sánh để hai bên chạy cùng task graph.

### Bước 4: So sánh Java và Gradle runtime

Thu thập:

~~~bash
java -version
javac -version
./gradlew --version
./gradlew javaToolchains
~~~

Ghi lại Gradle JVM trong IDE và Java runtime của CI. Kiểm tra plugin/Gradle compatibility trước khi thay target bytecode.

### Bước 5: So sánh working directory và environment

Xác nhận project root, JAVA_HOME, GRADLE_USER_HOME, proxy, profile và các biến cần thiết. Chỉ ghi log các giá trị không nhạy cảm.

Kiểm tra relative paths, case-sensitive file paths và file chỉ tồn tại local.

### Bước 6: Phân loại giai đoạn lỗi

Xác định lỗi xảy ra ở:

- Wrapper/Gradle startup.
- Settings/plugin resolution.
- Project configuration.
- Dependency resolution.
- Compile/generated source.
- Test.
- Packaging/verification.
- Application startup/deployment.

Giai đoạn lỗi giúp chọn đúng configuration/classpath cần điều tra.

### Bước 7: Thử build sạch trong workspace riêng

Chạy clean build với cache được kiểm soát. Không dùng chung build directory với invocation khác. Nếu cần, dùng Gradle User Home riêng để kiểm tra dependency resolution sạch.

### Bước 8: So sánh OS và tool ngoài

Nếu local Windows và CI Linux, kiểm tra case, permission, line endings, shell, path, encoding, locale và tool ngoài Java.

### Bước 9: Sửa nguyên nhân nhỏ nhất và chạy lại

Sau khi xác định khác biệt, sửa đúng nguồn cấu hình: Wrapper, toolchain, environment, repository, task input, path hoặc CI image. Chạy lại task thất bại rồi chạy lifecycle task liên quan.

## 14. Mẫu lệnh thu thập thông tin cho terminal và CI

Một bước diagnostic có thể in thông tin môi trường không nhạy cảm:

~~~bash
pwd
git rev-parse --show-toplevel
git rev-parse HEAD
git status --short
java -version
javac -version
./gradlew --version
./gradlew javaToolchains
~~~

Trên PowerShell:

~~~powershell
Get-Location
git rev-parse --show-toplevel
git rev-parse HEAD
git status --short
java -version
javac -version
.\gradlew.bat --version
.\gradlew.bat javaToolchains
~~~

Sau đó chạy task gây lỗi:

~~~bash
./gradlew :orders-service:build --stacktrace --info
~~~

Không nên mặc định bật --debug hoặc dump toàn bộ environment trong CI log; log mức quá chi tiết có thể chứa URL nội bộ, header hoặc thông tin nhạy cảm từ plugin. Nếu cần Build Scan hoặc log upload lên dịch vụ bên ngoài, hãy tuân theo chính sách dữ liệu của tổ chức.

## 15. Ví dụ cấu hình CI tối thiểu

Một job CI cần chọn rõ Java version và dùng Wrapper. Ví dụ shell step tổng quát:

~~~bash
java -version
./gradlew --version
./gradlew clean build --stacktrace
~~~

Nếu build dùng toolchain, runner cần có JDK được yêu cầu hoặc có cơ chế provision được cấu hình. Nếu dependency nằm trong repository riêng, job cần credentials qua secrets.

Với pipeline nhiều bước, cần bảo đảm mỗi step dùng đúng working directory. Nếu build cần generated files hoặc database service, khai báo bước setup trước khi chạy task tương ứng.

Không nên viết pipeline dựa vào state ngầm của runner, ví dụ file được tạo thủ công trong lần chạy trước hoặc dependency cache không được bảo đảm.

### 15.1. Dùng cùng Wrapper và baseline Java

Repository nên ghi rõ:

- Gradle Wrapper version.
- JDK dùng chạy Gradle.
- Java toolchain/compiler release.
- Java runtime tối thiểu của artifact.
- Các công cụ ngoài Java và version cần thiết.

CI nên thực hiện build/test trên baseline đã cam kết. Nếu sản phẩm hỗ trợ nhiều Java runtime, có thể có test matrix riêng thay vì chỉ test trên JDK mới nhất.

### 15.2. Cache CI phải được key theo môi trường phù hợp

Nếu CI restore Gradle User Home hoặc cache task, key cache nên phản ánh những yếu tố phù hợp như Gradle wrapper version, OS/architecture và các file dependency/config quan trọng theo chiến lược cache của pipeline.

Không chia sẻ trực tiếp thư mục build/ giữa các job song song. Dùng Gradle build cache để chia sẻ task outputs; mỗi job vẫn có workspace riêng.

## 16. Các triệu chứng thường gặp và hướng điều tra

| Triệu chứng | Khác biệt có thể có | Hướng điều tra |
|---|---|---|
| IDE compile pass, terminal compileJava fail | IDE compiler/JDK khác Gradle toolchain | Kiểm tra Gradle JVM, toolchain, compiler args |
| IDE sync pass, CI fail ở plugin resolution | Plugin repository, credential hoặc Gradle version khác | Kiểm tra settings, Wrapper và plugin repositories |
| IDE test pass, CI test fail | Test runner/JVM/classpath hoặc toàn bộ suite khác | Chạy cùng Gradle test task, kiểm tra test launcher |
| Local pass, CI cannot find symbol | Generated source hoặc annotation processor thiếu | Kiểm tra generator task và source set wiring |
| Windows pass, Linux fail | Path case, permission, line ending hoặc shell | Kiểm tra Git metadata và filesystem |
| Local pass, CI không tải được dependency | Cache local, proxy hoặc credential khác | Kiểm tra repository access và secrets |
| IDE pass, terminal fail khi chạy từ thư mục con | Working directory/build root khác | Dùng -p và project path rõ ràng |
| Chỉ fail khi parallel | Task race hoặc output collision | Chạy tuần tự để khoanh vùng, sửa task dependency/output |
| Build sạch fail nhưng build thường pass | File local/generated output hoặc cache che khác biệt | Kiểm tra untracked files và task inputs |
| CI fail sau khi nâng dependency | Version được resolve khác hoặc JDK baseline cao hơn | Dùng dependencyInsight và kiểm tra runtime requirement |
| App chạy local nhưng container fail | Runtime image/server JDK hoặc environment khác | Kiểm tra image cuối và java.home trong process |
| Chỉ fail trên CI runner mới | Tool ngoài hoặc OS image thay đổi | So sánh runner image, tool versions và resource limits |

## 17. Thiết kế project để build nhất quán ở mọi nơi

Một build đáng tin cậy không nên phụ thuộc vào trạng thái ngầm của IDE hoặc máy developer. Hãy làm cho mọi đầu vào cần thiết được thể hiện trong repository hoặc pipeline.

### 17.1. Dùng Gradle Wrapper

Commit Wrapper files và hướng dẫn dùng `./gradlew` hoặc `gradlew.bat`. Tránh yêu cầu mọi developer cài đúng một Gradle global version.

### 17.2. Khai báo toolchain và Java release

Dùng Java toolchain cho compiler/test launcher và `options.release` cho Java platform baseline. Ghi rõ JDK cần thiết để chạy Gradle và plugin.

### 17.3. Khai báo dependency và repository rõ ràng

Dùng version có kiểm soát, dependency locking khi phù hợp và repository settings rõ. Không dựa vào artifact đã cache trên máy developer.

### 17.4. Khai báo task inputs/outputs

Task custom phải khai báo inputs, outputs và task dependencies. Không đọc file hoặc environment ẩn rồi mong Gradle tự biết khi nào cần chạy lại.

### 17.5. Chuẩn hóa file và tool

Dùng `.gitattributes` cho line endings, encoding tường minh và path APIs portable. Ghi rõ tool ngoài Java cần cho build.

### 17.6. Tạo một lệnh kiểm tra chuẩn

README hoặc contributor guide nên cung cấp một lệnh CI-equivalent, ví dụ:

~~~bash
./gradlew clean build
~~~

Nếu CI có thêm task bắt buộc như integration test hoặc static analysis, hãy ghi rõ lệnh đó. Developer có thể chạy cùng command trước khi tạo pull request.

### 17.7. Kiểm thử trên môi trường tương tự production

Nếu production chạy Linux container với Java 17, cần có CI job chạy trên môi trường tương thích. Build trên Windows/JDK 21 không thay thế được kiểm thử runtime trên Linux/Java 17.

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| IDE Build Project pass nghĩa Gradle build pass | IDE có thể dùng compiler và task graph khác |
| Gradle sync thành công nghĩa tất cả test đã chạy | Sync chủ yếu cấu hình/import project |
| java -version cho biết JVM của Gradle | Phải kiểm tra ./gradlew --version và Gradle JVM setting |
| Có JDK mới trên máy thì Gradle tự dùng nó | IDE, daemon criteria, JAVA_HOME hoặc org.gradle.java.home có thể chọn JDK khác |
| Wrapper khóa cả Gradle và JDK | Wrapper khóa Gradle distribution; JVM chạy Gradle là cấu hình riêng |
| Java toolchain thay đổi Gradle daemon JVM | Toolchain chọn compiler/test launcher cho task |
| Local pass chứng minh source tree sạch | File untracked/generated hoặc cấu hình cá nhân có thể che lỗi |
| CI fail luôn là lỗi của CI | CI có thể làm lộ dependency hoặc environment assumption vốn không được khai báo |
| Xóa cache sẽ sửa mọi lỗi local/CI | Cache chỉ là một yếu tố; không sửa JDK, path, credentials hoặc task graph |
| Giảm worker là cách sửa race lâu dài | Cần sửa shared state và output collision trong task |
| Copy toàn bộ .gradle từ máy developer sang CI là tốt | Có thể mang theo init script, credential và state cá nhân |
| Build pass trên JDK mới chứng minh tương thích JDK cũ | Cần compile release phù hợp và test trên runtime baseline |

## 19. Checklist khi build chỉ lỗi ở terminal hoặc CI

Trước khi thay đổi cấu hình, hãy thu thập:

- [ ] IDE action nào đã thành công: Sync, Build, Run, test hay Gradle task?
- [ ] IDE có delegate build/run sang Gradle không?
- [ ] IDE và terminal có chạy cùng Gradle Wrapper version không?
- [ ] Gradle JVM trong IDE và JVM trong terminal/CI có giống nhau không?
- [ ] Java toolchain và options.release có được khai báo rõ không?
- [ ] Test launcher có dùng đúng Java version không?
- [ ] Cùng một commit và cùng source files được build ở hai môi trường không?
- [ ] Task và project path có giống nhau không?
- [ ] Working directory có đúng Gradle root không?
- [ ] JAVA_HOME, GRADLE_USER_HOME, proxy và profile có phù hợp không?
- [ ] CI có credential để truy cập dependency/plugin repository không?
- [ ] Generated sources và annotation processors có được chạy qua Gradle không?
- [ ] File paths có phân biệt case hoặc phụ thuộc Windows không?
- [ ] Line endings, encoding, permission và shell có khác nhau không?
- [ ] Có file untracked hoặc cấu hình cá nhân khiến local pass không?
- [ ] CI runner có đủ JDK và tool ngoài Java không?
- [ ] Build có race khi chạy parallel hoặc nhiều job dùng chung output không?
- [ ] Cache có đang che thiếu dependency hoặc task input không?
- [ ] Đã tái hiện bằng Wrapper trong workspace sạch chưa?
- [ ] Đã chạy smoke test trên runtime gần production chưa?

## Kết luận

Build chạy được trong IDE nhưng lỗi ở terminal hoặc CI thường xuất phát từ sự khác biệt trong công cụ thực thi, JVM, task graph, working directory, environment, dependency resolution, filesystem hoặc trạng thái cache. Bước đầu tiên là xác định IDE đã chạy Gradle thật hay dùng compiler/test runner riêng, rồi chạy cùng Gradle Wrapper và cùng task để tạo phép so sánh có ý nghĩa.

Hãy thu thập Java/Gradle version từ đúng process, xác nhận toolchain và runtime baseline, kiểm tra root directory và environment, sau đó phân loại lỗi theo giai đoạn configuration, dependency, compile, test hay deployment. CI nên dùng Wrapper, checkout sạch, JDK/toolchain rõ ràng, credentials qua secret store và workspace riêng cho từng job. Khi build không còn phụ thuộc vào cấu hình cá nhân hoặc file chỉ có trên máy developer, kết quả sẽ nhất quán hơn giữa IDE, terminal và CI.
