# Xác định lỗi thuộc môi trường, cấu hình hay thực thi tác vụ

Khi một lệnh Gradle thất bại, thông báo cuối cùng thường chỉ cho biết build đã dừng ở đâu. Muốn tìm đúng nguyên nhân, cần xác định lỗi xuất hiện trong giai đoạn nào và thành phần nào chịu trách nhiệm: môi trường chạy Gradle, cấu hình build, quá trình phân giải dependency hay action của một task.

Ví dụ, lỗi không tìm thấy JDK có thể xảy ra trước khi Gradle đọc build script. Lỗi plugin không tìm thấy thường xảy ra khi Gradle cấu hình build và phân giải plugin. Lỗi biên dịch Java xảy ra khi task compiler thực thi. Cả ba đều làm lệnh build trả về mã lỗi, nhưng cách xử lý hoàn toàn khác nhau.

Bài này trình bày một quy trình chẩn đoán theo vòng đời build, giúp thu hẹp nguyên nhân trước khi thay đổi code hoặc cấu hình.

## 1. Bắt đầu từ vòng đời của một Gradle build

Một lần gọi Gradle thường đi qua ba giai đoạn chính: initialization, configuration và execution. Trước các giai đoạn này, Gradle Wrapper và JVM cũng phải khởi động thành công.

~~~text
Lệnh ./gradlew ...
       |
       v
Gradle Wrapper / JVM startup
Tìm wrapper, tải distribution nếu cần,
chọn JVM và khởi động Gradle
       |
       v
1. Initialization
Đọc settings.gradle(.kts)
Tạo Gradle và Project model
Xác định các project trong build
       |
       v
2. Configuration
Đọc build.gradle(.kts)
Áp dụng plugin
Cấu hình task và dependency
Xây dựng task graph
       |
       v
Dependency / variant resolution
Tìm component, version, artifact phù hợp
       |
       v
3. Execution
Chạy task theo graph
Compile, test, package, copy, deploy...
       |
       v
Build result
SUCCESS hoặc FAILED
~~~

| Giai đoạn | Gradle đang làm gì? | Ví dụ lỗi thường gặp |
|---|---|---|
| Wrapper/JVM startup | Tìm Gradle distribution, chọn JVM và khởi động | Không tải được distribution, sai JDK, JVM không khởi động |
| Initialization | Đọc settings, xác định root project, included builds và project | Không đọc được settings, project path sai |
| Configuration | Đọc build script, áp dụng plugin, cấu hình task | Syntax error, plugin không tìm thấy, cấu hình task không hợp lệ |
| Dependency resolution | Tìm module, version, metadata, variant và artifact | Repository lỗi, thiếu credential, không có variant tương thích |
| Execution | Thực thi task và chương trình bên ngoài | Compile error, test fail, permission denied khi ghi output |

Dependency resolution có thể được kích hoạt trong những thời điểm khác nhau vì Gradle dùng cấu hình lazy. Một số configuration chỉ được resolve khi task cần đến chúng. Do đó, lỗi resolve dependency có thể xuất hiện trong lúc Gradle chuẩn bị task hoặc ngay trước khi task chạy.

Điểm cần nhớ: tên task xuất hiện trong log không tự động có nghĩa lỗi nằm trong task action. Gradle có thể đang resolve input hoặc cấu hình task đó trước khi thực thi.

## 2. Ba nhóm nguyên nhân chính

Có thể bắt đầu bằng ba nhóm lớn:

**Lỗi môi trường** xảy ra khi máy hoặc tiến trình Gradle không có điều kiện cần thiết để chạy: JDK không phù hợp, thiếu quyền, hết dung lượng, network/proxy lỗi, file bị khóa hoặc tiến trình không khởi động được.

**Lỗi cấu hình** xảy ra khi Gradle không thể xây dựng build model hợp lệ: settings/build script sai, plugin không áp dụng được, project path không tồn tại, property thiếu hoặc task được cấu hình không hợp lệ.

**Lỗi thực thi task** xảy ra sau khi Gradle đã xây dựng task graph và bắt đầu chạy công việc: compiler thất bại, test thất bại, task đọc/ghi file lỗi hoặc chương trình con trả về exit code khác 0.

Dependency resolution là một điểm cần nhận diện riêng khi chẩn đoán. Nó thường gắn với cấu hình dependency và repository, nhưng cũng chịu ảnh hưởng của môi trường mạng, credential, metadata và variant.

| Nhóm | Câu hỏi đầu tiên | Bằng chứng thường thấy |
|---|---|---|
| Môi trường | Gradle/JVM có thể khởi động và truy cập tài nguyên cần thiết không? | Wrapper, JVM, permission, network, disk, lock |
| Cấu hình | Gradle có thể đọc và cấu hình build hợp lệ không? | Settings, build script, plugin, property, task configuration |
| Resolution | Gradle có tìm được dependency/variant cần thiết không? | Repository, version, metadata, credentials, variant |
| Thực thi | Task action hoặc process nào đã thất bại? | Compiler, test worker, archive, external process, output file |

Một lỗi có thể liên quan đến nhiều nhóm. Ví dụ, compile task báo thiếu class có thể do code import sai, compile classpath thiếu dependency hoặc dependency resolution thất bại. Cần lần theo bằng chứng thay vì phân loại chỉ từ một dòng thông báo.

## 3. Bước đầu tiên: xác định lệnh và môi trường thực sự được dùng

Trước khi sửa build, ghi lại cách lệnh được gọi. Cùng một repository có thể chạy bằng những môi trường khác nhau:

- Gradle Wrapper trong terminal.
- Gradle được cài toàn hệ thống.
- Gradle chạy từ IDE.
- CI runner với biến môi trường và secret riêng.
- Container hoặc remote build agent.

Nếu terminal dùng Wrapper nhưng IDE dùng một Gradle distribution khác, kết quả có thể khác nhau. Nếu terminal và IDE chọn JDK khác nhau, lỗi có thể chỉ xuất hiện ở một nơi.

### Luôn kiểm tra Gradle Wrapper

Trong project có Wrapper, ưu tiên chạy:

~~~shell
./gradlew build
~~~

Trên Windows:

~~~powershell
.\gradlew.bat build
~~~

Wrapper chọn Gradle distribution được khai báo trong file:

~~~text
gradle/wrapper/gradle-wrapper.properties
~~~

Ví dụ:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
~~~

Nếu Wrapper chưa tải được distribution, build có thể thất bại trước khi đọc settings hoặc build script. Trong trường hợp này, xem URL, network, proxy, TLS certificate, quyền ghi vào Gradle User Home và dung lượng đĩa.

Không nên thay Wrapper bằng một lệnh Gradle cài toàn hệ thống chỉ để thử nhanh mà không ghi lại sự khác biệt về version. Điều đó có thể che giấu lỗi tương thích giữa Wrapper và môi trường.

### Ghi nhận version và JVM

Chạy:

~~~shell
./gradlew --version
~~~

Lệnh này giúp xác định Gradle version, JVM đang chạy Gradle và thông tin môi trường liên quan. Nếu lệnh này cũng thất bại, hãy xử lý vấn đề Wrapper/JVM trước khi điều tra task.

Đối chiếu thêm:

~~~shell
java -version
javac -version
~~~

Hai lệnh này cho biết Java được tìm thấy qua PATH. Chúng không nhất thiết là JDK mà Gradle daemon hoặc IDE đang sử dụng.

## 4. Phân biệt JVM chạy Gradle với Java toolchain

Một nguyên nhân thường gây nhầm lẫn là project có thể dùng nhiều JDK cho các mục đích khác nhau.

- **Gradle JVM** là JVM chạy Gradle daemon và build logic.
- **Java toolchain** là JDK/JRE được task Java chọn để compile, test hoặc chạy Java tool.
- **IDE Gradle JVM** là JVM IDE dùng khi import/sync hoặc chạy Gradle từ IDE.
- **JAVA_HOME/PATH** ảnh hưởng cách shell tìm Java và cách Wrapper/Gradle được khởi động, tùy cấu hình.

Ví dụ:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Project yêu cầu toolchain Java 21 cho các task Java phù hợp. Điều đó không tự động có nghĩa Gradle daemon cũng phải chạy bằng Java 21. Gradle daemon cần một JVM tương thích với phiên bản Gradle đang dùng; toolchain phục vụ compiler/runtime của project.

### Dấu hiệu lỗi JDK/JVM

| Thông báo hoặc triệu chứng | Hướng điều tra |
|---|---|
| JAVA_HOME is set to an invalid directory | Kiểm tra đường dẫn và JDK tại JAVA_HOME |
| Could not determine java version | Kiểm tra Java được Wrapper/Gradle chọn và khả năng tương thích |
| Unsupported class file major version | Kiểm tra JDK/Gradle/plugin đọc hoặc chạy bytecode phiên bản nào |
| No matching toolchains found | Kiểm tra toolchain yêu cầu, JDK đã cài và cấu hình toolchain download |
| Build chạy trong terminal nhưng lỗi ở IDE | So sánh Gradle JVM và Gradle distribution của IDE |
| Compiler dùng sai Java version | Kiểm tra Java toolchain và task compiler |

### Kiểm tra cấu hình Java

Tìm các thiết lập liên quan:

- JAVA_HOME và PATH của terminal.
- org.gradle.java.home trong gradle.properties hoặc cấu hình người dùng.
- Java toolchain trong build script/convention plugin.
- Gradle JVM trong IDE.
- JDK cài trên máy hoặc được cung cấp bởi CI image.

Không thay đổi đồng thời mọi thiết lập. Trước tiên xác định JVM nào thực sự được dùng ở giai đoạn thất bại.

## 5. Lỗi môi trường: Wrapper, daemon, network và tài nguyên máy

Nếu Gradle chưa thể khởi động hoặc không truy cập được tài nguyên cần thiết, hãy điều tra môi trường trước.

### Wrapper không tải được Gradle distribution

Các nguyên nhân có thể gồm:

- Không truy cập được URL distribution.
- Proxy không được cấu hình cho tiến trình Gradle.
- TLS inspection hoặc certificate của tổ chức không được JVM tin cậy.
- Máy chủ distribution tạm thời không khả dụng.
- Không có quyền ghi vào Gradle User Home.
- Dung lượng đĩa không đủ để tải/giải nén distribution.

Kiểm tra distributionUrl, network/proxy và log của Wrapper. Nếu máy chỉ thất bại khi tải distribution lần đầu, nhưng chạy được sau khi distribution đã có trong cache, đây là dấu hiệu cần điều tra truy cập mạng hoặc quyền ghi cache.

### Gradle daemon

Gradle daemon là tiến trình nền được tái sử dụng giữa các lần build. Daemon giúp tránh chi phí khởi động JVM và nạp build logic lặp lại.

Có thể kiểm tra trạng thái:

~~~shell
./gradlew --status
~~~

Dừng daemon:

~~~shell
./gradlew --stop
~~~

Sau đó chạy lại build để xem lỗi có liên quan đến trạng thái tiến trình nền hay không.

Một số tình huống đáng xem xét:

- Daemon bị dừng do thiếu bộ nhớ.
- JVM daemon dùng option không tương thích.
- Daemon cũ giữ trạng thái môi trường hoặc file handle.
- Plugin hoặc build logic gây lỗi trong tiến trình daemon.
- Máy có giới hạn process/thread hoặc tài nguyên hệ thống.

Dừng daemon là phép thử có kiểm soát; nó không tự sửa lỗi cấu hình hoặc lỗi code. Nếu lỗi tái diễn, xem log daemon tương ứng với Gradle version và thời điểm chạy.

Log daemon thường nằm trong Gradle User Home dưới cấu trúc:

~~~text
caches/
  ...
daemon/
  <gradle-version>/
    daemon-<pid>.out.log
~~~

Vị trí thực tế phụ thuộc Gradle User Home. Có thể xác định Gradle User Home qua môi trường hoặc cấu hình người dùng.

### Network, proxy và repository

Một lỗi network có thể xuất hiện khi resolve plugin hoặc dependency. Cần phân biệt:

- Không truy cập được Gradle distribution.
- Không truy cập được plugin repository.
- Không truy cập được dependency repository.
- DNS/TLS/proxy lỗi.
- Repository yêu cầu authentication.
- Server trả về HTTP 401, 403, 404 hoặc 5xx.

Các loại repository có thể được cấu hình ở những vị trí khác nhau. Plugin DSL thường dùng pluginManagement.repositories trong settings; dependency của project dùng repositories trong build script hoặc dependency resolution management.

Nếu plugin không resolve được, thêm repository vào repositories của project có thể không giải quyết đúng vấn đề. Hãy kiểm tra repository ở đúng lớp.

### Quyền truy cập, file lock và dung lượng

Các thông báo như AccessDeniedException, Permission denied, Read-only file system, No space left on device hoặc lỗi tạo thư mục thường chỉ ra vấn đề môi trường/filesystem.

Kiểm tra:

- User chạy Gradle có quyền đọc source và ghi thư mục build không.
- Gradle User Home có quyền ghi không.
- Antivirus/indexer có đang khóa file output không.
- Có tiến trình khác đang sử dụng file không.
- Dung lượng đĩa và inode có đủ không.
- Path có quá dài hoặc chứa ký tự không được công cụ bên ngoài hỗ trợ không.
- CI workspace có quyền sở hữu đúng không.

Không xóa Gradle cache hoặc thư mục build hàng loạt khi chưa xác định file nào bị lỗi. Trước tiên đọc exception đầy đủ và xác định đường dẫn cụ thể.

## 6. Lỗi initialization và settings

Initialization xảy ra trước khi Gradle cấu hình từng project. Các vấn đề ở đây thường liên quan đến settings và cấu trúc build.

Các file thường cần xem:

~~~text
settings.gradle
settings.gradle.kts
gradle.properties
buildSrc/
build-logic/
included build settings
~~~

### Project path không tồn tại

Ví dụ settings:

~~~groovy
rootProject.name = 'shop'
include 'app', 'domain', 'shared'
~~~

Nếu project được include nhưng thư mục không tồn tại hoặc projectDir ánh xạ sai, Gradle có thể không tạo được project model như mong đợi.

Ánh xạ project directory:

~~~groovy
include 'domain'
project(':domain').projectDir = file('modules/domain-core')
~~~

Khi gặp lỗi không tìm thấy project, kiểm tra:

- Project path được viết đúng chưa.
- Project đã được include trong settings chưa.
- projectDir có trỏ đến thư mục hợp lệ không.
- Settings của included build có hợp lệ không.
- Lệnh đang được chạy từ đúng root build không.

### Lỗi settings plugin và pluginManagement

Plugin được khai báo trong settings hoặc plugin DSL có thể cần repository riêng.

Ví dụ:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
~~~

Nếu settings plugin hoặc plugin được áp dụng qua plugins block không resolve được, hãy kiểm tra pluginManagement, plugin ID, version và repository. Đừng nhầm lớp resolve plugin với dependency repository của project.

### Included build và build logic

Một build có thể include build logic riêng:

~~~groovy
pluginManagement {
    includeBuild('build-logic')
}
~~~

Included build vẫn là một build riêng có settings, project model và lifecycle riêng. Gradle có thể kết nối component giữa các build qua composite build substitution hoặc plugin management theo cấu hình.

Nếu included build có settings/build script lỗi, root build có thể thất bại ngay trong initialization hoặc configuration. Khi đó, lỗi có thể không nằm trong project app đang được build.

Hãy đọc project path và file path trong stacktrace để xác định build nào thực sự thất bại.

## 7. Lỗi configuration: build script, plugin và project model

Configuration phase đọc build script, áp dụng plugin, tạo task và thiết lập các property. Lỗi trong giai đoạn này thường xảy ra trước khi task action chạy.

Ví dụ:

~~~groovy
plugins {
    id 'java'
}

tasks.register('packageApp') {
    dependsOn tasks.named('jar')
}
~~~

Nếu build script có syntax error, gọi API không tồn tại hoặc tham chiếu task sai, Gradle có thể thất bại trong lúc cấu hình.

### Lỗi cú pháp DSL

Ví dụ Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.example:library:1.0'
}
~~~

Ví dụ Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.example:library:1.0")
}
~~~

Không thể dùng cú pháp Groovy trực tiếp trong Kotlin DSL hoặc ngược lại. Cần xác định đúng loại file:

- build.gradle: Groovy DSL.
- build.gradle.kts: Kotlin DSL.
- settings.gradle: Groovy settings DSL.
- settings.gradle.kts: Kotlin settings DSL.

Thông báo compile/syntax error có thể chỉ vào dòng cụ thể, nhưng nguyên nhân đôi khi nằm ở một file được apply từ nơi khác hoặc convention plugin.

### Plugin không tìm thấy hoặc không tương thích

Ví dụ:

~~~groovy
plugins {
    id 'com.example.custom-plugin' version '1.4'
}
~~~

Các khả năng:

- Plugin ID sai.
- Version không tồn tại.
- Plugin repository chưa được khai báo.
- Repository không truy cập được.
- Plugin yêu cầu Gradle/JDK khác.
- Plugin được khai báo trong buildSrc hoặc included build nhưng build logic đó lỗi.
- Plugin đã được cung cấp ở nơi khác và không thể khai báo version theo cách hiện tại.

Đọc thông báo plugin resolution và stacktrace trước khi thay đổi version ngẫu nhiên. Nếu plugin được resolve nhưng lỗi khi apply, đó là lỗi cấu hình plugin, khác với lỗi không tìm thấy artifact.

### Property bắt buộc bị thiếu

Build script hoặc plugin có thể yêu cầu project property:

~~~groovy
def environmentName = providers.gradleProperty('environmentName')
    .get()
~~~

Nếu property không được truyền, Gradle có thể báo lỗi trong configuration phase.

Có thể cung cấp qua command line:

~~~shell
./gradlew build -PenvironmentName=staging
~~~

Hoặc cấu hình property theo chính sách của project/user/CI. Cần xác định property được đọc ở đâu và giá trị nào là hợp lệ; không tự thêm giá trị giả chỉ để làm build chạy qua.

### Task configuration không hợp lệ

Ví dụ task yêu cầu file input nhưng file chưa được cấu hình:

~~~groovy
tasks.register('inspectConfig') {
    inputs.file(layout.projectDirectory.file('config/app.json'))
}
~~~

Nếu task configuration hoặc plugin truy cập property bắt buộc quá sớm, build có thể thất bại trước execution. Hãy phân biệt property chưa được set, file không tồn tại, và task action không đọc được file khi chạy.

## 8. Dependency resolution: phân biệt repository, version và variant

Dependency resolution thường là ranh giới giữa cấu hình và thực thi. Gradle có thể đã cấu hình task nhưng chưa thể thực hiện vì input dependency không resolve được.

Ví dụ:

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.example:service-client:2.0'
}
~~~

Thông báo như:

~~~text
Could not resolve all files for configuration ':app:runtimeClasspath'.
Could not find org.example:service-client:2.0.
~~~

cho biết configuration không lấy được dependency. Cần điều tra:

- Tọa độ group/module/version có chính xác không.
- Version có tồn tại trong repository không.
- Repository có được khai báo trong đúng scope không.
- Network, proxy, TLS và DNS có hoạt động không.
- Credential có hợp lệ và có quyền đọc artifact không.
- Metadata của module có hợp lệ không.
- Dependency constraints hoặc resolution rules có ảnh hưởng không.
- Variant được consumer yêu cầu có tồn tại không.

### Plugin repository và dependency repository

Hai nhóm repository không thể thay thế nhau một cách tùy ý:

| Loại | Nơi cấu hình thường gặp | Phục vụ |
|---|---|---|
| Plugin repository | pluginManagement.repositories trong settings | Resolve plugin được khai báo qua plugin DSL |
| Dependency repository | repositories trong project hoặc dependencyResolutionManagement | Resolve thư viện và artifact của project |
| Buildscript repository | buildscript.repositories | Resolve classpath cho legacy buildscript dependencies |

Nếu plugin không tìm thấy, kiểm tra plugin repository. Nếu thư viện runtime không tìm thấy, kiểm tra dependency repository của configuration tương ứng.

### Không có variant phù hợp

Một dependency có thể tồn tại nhưng Gradle vẫn không chọn được variant phù hợp.

Ví dụ, consumer yêu cầu Java 21 nhưng producer chỉ công bố variant cho target JVM thấp hơn hoặc có attributes khác. Thông báo thường nói không có variant nào phù hợp hoặc nêu attributes consumer/producer không tương thích.

Hướng xử lý:

1. Xác định configuration consumer, ví dụ compileClasspath hoặc runtimeClasspath.
2. Đọc attributes consumer đang yêu cầu.
3. Đọc variants producer công bố.
4. Kiểm tra target JVM, usage, category, library elements và custom attributes.
5. Sửa metadata/toolchain/variant phù hợp ở đúng phía.

Không thêm JAR bằng file path để lách variant mismatch nếu dependency cần tham gia resolution như một component.

### Version conflict không nhất thiết là lỗi

Gradle có thể chọn một version trong số nhiều version được yêu cầu theo quy tắc resolution. Muốn biết lý do chọn version:

~~~shell
./gradlew :app:dependencyInsight --dependency service-client --configuration runtimeClasspath
~~~

Lệnh này giúp xem các nhánh dependency và lý do một version được chọn. Nếu build thực sự thất bại do strict constraint hoặc resolution rule, report sẽ giúp tìm nguồn yêu cầu.

## 9. Lỗi execution: xác định task action nào thất bại

Khi Gradle đã cấu hình build và bắt đầu execution, log thường hiển thị task path đang chạy.

Ví dụ:

~~~text
> Task :domain:compileJava FAILED
> Task :app:test SKIPPED
~~~

Task :domain:compileJava là nơi lỗi được báo. Tuy nhiên, vẫn cần đọc exception để phân biệt lỗi source code, compile classpath, toolchain hoặc filesystem.

### Compile task

Lỗi compiler thường có thông tin như:

- cannot find symbol
- package ... does not exist
- incompatible types
- error: ...
- Compiler process exited with non-zero code

Nguyên nhân có thể là:

- Code Java không hợp lệ.
- Import hoặc package sai.
- Compile dependency thiếu.
- Compile classpath/variant không đúng.
- Annotation processor không hoạt động.
- JDK/toolchain không đúng.
- Generated source chưa được tạo hoặc chưa được nối vào source set.

Nếu lỗi là cannot find symbol, đừng vội kết luận chỉ là lỗi code. Kiểm tra classpath và generated source nếu symbol đến từ module/dependency khác.

### Test task

Test task có thể thất bại vì:

- Assertion fail.
- Exception trong test hoặc application code.
- Test engine không tìm thấy test.
- Test worker không khởi động.
- JVM test process bị kill hoặc hết bộ nhớ.
- Test phụ thuộc service/database bên ngoài.
- Test dùng resource hoặc file không có trong môi trường CI.

Phân biệt test assertion failure với lỗi khởi động worker. Báo cáo test và log worker thường cung cấp chi tiết hơn dòng :test FAILED.

Ví dụ chạy test có log:

~~~shell
./gradlew :app:test --info --stacktrace
~~~

Nếu cần tập trung vào một test:

~~~shell
./gradlew :app:test --tests "com.example.OrderServiceTest"
~~~

Test filter giúp cô lập một nhóm test; nó không sửa môi trường hoặc dependency bị thiếu.

### Task chạy external process

Một task có thể gọi compiler, Node, Docker, shell script, database migration tool hoặc chương trình khác. Khi process trả exit code khác 0, Gradle có thể báo:

~~~text
Process 'command ...' finished with non-zero exit value 1
~~~

Điều này cho biết process con thất bại. Đọc stdout/stderr của process, command line thực tế, working directory, environment và file input của nó.

Kiểm tra:

- Executable có tồn tại trên PATH không.
- Version tool có đúng không.
- Process có quyền đọc/ghi file không.
- Working directory có đúng không.
- Biến môi trường và credential có được truyền không.
- Service bên ngoài có sẵn sàng không.
- Exit code có ý nghĩa gì theo tài liệu của tool.

Đừng sửa Gradle task chỉ vì nó là nơi báo lỗi nếu nguyên nhân thật sự nằm trong chương trình con.

## 10. Đọc log: bắt đầu từ lỗi đầu tiên có ý nghĩa

Một build thất bại có thể in nhiều dòng exception. Các task downstream có thể bị skip hoặc thất bại do một output không được tạo. Dòng cuối cùng không nhất thiết là nguyên nhân gốc.

Một thứ tự đọc hữu ích:

1. Tìm dòng FAILURE: Build failed with an exception.
2. Đọc phần What went wrong?.
3. Xác định task/project path nếu có.
4. Đọc exception đầu tiên có ý nghĩa và các dòng Caused by.
5. Đối chiếu với task đang thực thi hoặc giai đoạn Gradle đang ở.
6. Bỏ qua các lỗi downstream chỉ là hệ quả cho đến khi có bằng chứng độc lập.

Ví dụ:

~~~text
> Task :app:compileJava FAILED

Execution failed for task ':app:compileJava'.
> Compilation failed; see the compiler output below.

error: package com.example.domain does not exist
~~~

Thông tin này cho thấy compile task thất bại vì compiler không thấy package. Cần xem compileClasspath, project dependency và source/package declaration trước khi sửa task execution.

Một ví dụ khác:

~~~text
Could not resolve all files for configuration ':app:compileClasspath'.
Could not find com.example:domain-api:2.0.
~~~

Ở đây compile task có thể chưa chạy compiler. Lỗi xảy ra khi resolve input classpath. Điều tra repository, tọa độ dependency và network trước.

### Caused by và exception lồng nhau

Một exception Gradle có thể bọc exception từ compiler, filesystem, network hoặc process con. Đọc các lớp exception để tìm nguyên nhân cụ thể.

Ví dụ:

- Gradle task exception bao một IOException.
- IOException bao AccessDeniedException.
- Task failure chỉ là lớp ngoài cùng; vấn đề thật là quyền filesystem.

Stacktrace đầy đủ giúp nối các lớp này.

## 11. Chọn mức log phù hợp

Không cần bắt đầu bằng log chi tiết nhất. Tăng dần mức thông tin theo câu hỏi đang cần trả lời.

| Tùy chọn | Mục đích |
|---|---|
| Không thêm tùy chọn | Xem lỗi và task outcome cơ bản |
| --stacktrace | Xem stacktrace của lỗi |
| --info | Xem thêm thông tin configuration, task và dependency/cache behavior |
| --debug | Log rất chi tiết cho điều tra sâu |
| --scan | Tạo Build Scan để quan sát build nếu dịch vụ/plugin được cấu hình và được phép dùng |

Ví dụ:

~~~shell
./gradlew build --stacktrace
~~~

Khi cần thêm ngữ cảnh:

~~~shell
./gradlew build --info --stacktrace
~~~

Dùng debug có chọn lọc:

~~~shell
./gradlew build --debug
~~~

Debug log có thể rất dài và có thể chứa đường dẫn nội bộ, thông tin repository, biến môi trường hoặc dữ liệu nhạy cảm do plugin/task ghi ra. Trước khi chia sẻ log, hãy kiểm tra và che credential/token, URL nội bộ và dữ liệu nhạy cảm.

Build Scan có thể cung cấp timeline và thông tin task chi tiết, nhưng việc tạo scan có thể gửi dữ liệu build đến dịch vụ được cấu hình. Tuân thủ chính sách tổ chức trước khi publish hoặc chia sẻ scan.

## 12. Dùng task graph để xác định phạm vi lỗi

Task graph cho biết Gradle dự kiến chạy những task nào và các dependency giữa chúng.

Xem task:

~~~shell
./gradlew tasks --all
~~~

Xem thông tin task:

~~~shell
./gradlew help --task test
~~~

Xem graph mà không thực thi task action:

~~~shell
./gradlew build --dry-run
~~~

Với build nhiều project, dùng task path rõ ràng:

~~~shell
./gradlew :app:compileJava
~~~

Điều này giúp giảm phạm vi điều tra. Nếu chỉ gọi build, nhiều task ở nhiều project có thể được chọn và lỗi xuất hiện ở một project không liên quan trực tiếp đến thay đổi đang xem.

### Phân biệt task dependency và thứ tự task

dependsOn thêm task dependency vào graph. mustRunAfter và shouldRunAfter chỉ ràng buộc thứ tự nếu các task liên quan đã được chọn. Nếu consumer cần output của producer, cần khai báo dependency/input-output đúng; chỉ sắp xếp thứ tự không bảo đảm output được tạo.

Khi task bị skip, kiểm tra lý do skip và dependency của nó. UP-TO-DATE, FROM-CACHE, NO-SOURCE và SKIPPED có ý nghĩa khác nhau; không phải trạng thái nào cũng là lỗi.

## 13. Cô lập lỗi bằng một lệnh nhỏ hơn

Sau khi đọc lỗi, hãy giảm phạm vi build theo cách vẫn giữ nguyên điều kiện cần thiết.

Ví dụ, nếu build đầy đủ thất bại tại compile của :app:

~~~shell
./gradlew :app:compileJava --stacktrace
~~~

Nếu compile task vẫn thất bại, kiểm tra classpath:

~~~shell
./gradlew :app:dependencies --configuration compileClasspath
~~~

Nếu nghi ngờ một dependency cụ thể:

~~~shell
./gradlew :app:dependencyInsight --dependency domain-api --configuration compileClasspath
~~~

Nếu task phụ thuộc output do generator tạo, gọi consumer trực tiếp để kiểm tra graph:

~~~shell
./gradlew :app:compileJava --dry-run
~~~

Sau đó chạy task thực tế với --info để xác nhận producer và consumer được thực thi đúng.

### Cô lập có kiểm soát

Không nên thay đổi đồng thời JDK, dependency version, plugin version và repository chỉ để thử. Nếu build bắt đầu chạy, sẽ khó biết thay đổi nào giải quyết nguyên nhân.

Thay vào đó:

- Ghi lại lệnh gốc và môi trường.
- Chọn một giả thuyết.
- Thay đổi một yếu tố.
- Chạy lại lệnh tối thiểu có thể tái hiện.
- So sánh lỗi trước và sau.
- Giữ lại thông tin để có thể tái hiện.

## 14. Ma trận triệu chứng và hướng điều tra

| Triệu chứng | Nhóm cần kiểm tra đầu tiên | Bước tiếp theo |
|---|---|---|
| Wrapper không tải distribution | Môi trường | URL, proxy, TLS, quyền ghi, disk |
| JAVA_HOME sai hoặc JVM không khởi động | Môi trường | JDK path, Gradle JVM, Gradle version |
| Build chỉ lỗi trên IDE | Môi trường/cấu hình IDE | Gradle JVM, Wrapper setting, environment |
| Không đọc được settings file | Initialization/môi trường | File path, permission, syntax |
| Project path không tồn tại | Cấu hình settings | include, projectDir, root build |
| Plugin không tìm thấy | Plugin resolution/cấu hình | Plugin ID/version, pluginManagement.repositories |
| Không resolve được dependency | Dependency resolution | Coordinates, repositories, credentials, network |
| Không có variant phù hợp | Dependency/variant configuration | Attributes, target JVM, producer variants |
| Build script syntax error | Cấu hình | DSL, dòng lỗi, file được apply |
| Task/property chưa được cấu hình | Cấu hình | Provider/property convention và required value |
| Compiler báo cannot find symbol | Thực thi compile hoặc compile classpath | Source, imports, dependency, generated source |
| Test assertion fail | Thực thi test | Test report, application behavior |
| Test worker không khởi động | Môi trường/thực thi test | Test JVM, memory, process log |
| AccessDeniedException khi ghi output | Môi trường/thực thi | Quyền thư mục, file lock, antivirus |
| External process exit code khác 0 | Thực thi process con | Command, stdout/stderr, environment |
| Configuration cache không lưu được | Cấu hình/build logic | Plugin/task compatibility và report |
| Task liên tục chạy lại | Task input/output hoặc cache | Input snapshot, output, cacheability |

Ma trận chỉ xác định nơi bắt đầu. Một lỗi có thể đi qua nhiều lớp; cần dùng stacktrace và log để xác nhận.

## 15. Ví dụ chẩn đoán: build lỗi vì JDK

Giả sử CI báo lỗi khi chạy Wrapper:

~~~text
Could not determine java version from '...'
~~~

Quy trình:

1. Chạy ./gradlew --version để xem Wrapper có khởi động được không.
2. Kiểm tra JDK mà tiến trình CI dùng qua JAVA_HOME và PATH.
3. Kiểm tra Gradle Wrapper version trong gradle-wrapper.properties.
4. Đối chiếu yêu cầu JDK của Gradle version đó.
5. Kiểm tra CI image và IDE có đang dùng cùng JDK hay không.

Nếu Wrapper không khởi động, chưa cần điều tra compileJava hoặc test. Lỗi xảy ra trước execution.

## 16. Ví dụ chẩn đoán: plugin không tìm thấy

Giả sử build báo:

~~~text
Plugin [id: 'com.example.company-plugin', version: '1.2'] was not found
~~~

Quy trình:

1. Xác nhận plugin ID và version có chính xác.
2. Xem pluginManagement.repositories trong settings.
3. Kiểm tra plugin marker/artifact có được publish lên repository dự kiến không.
4. Kiểm tra credential, proxy và network.
5. Nếu plugin nằm trong included build hoặc build logic nội bộ, xác nhận included build được khai báo đúng và cấu hình thành công.

Không bắt đầu bằng cách thêm dependency vào implementation. Plugin resolution và project dependency resolution là hai cơ chế khác nhau.

## 17. Ví dụ chẩn đoán: compile không tìm thấy package

Giả sử compiler báo:

~~~text
error: package com.example.domain.api does not exist
~~~

Có ít nhất ba hướng cần kiểm tra:

**Source code:** package declaration hoặc import có đúng không? Class/interface có thực sự nằm trong source set được biên dịch không?

**Compile classpath:** project consumer đã khai báo implementation project(':domain') hoặc dependency tương ứng chưa? Project producer có export package cần thiết qua module/variant không?

**Dependency resolution:** configuration compileClasspath có resolve được producer/dependency không? Có variant mismatch hoặc version conflict không?

Dùng:

~~~shell
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencyInsight --dependency domain-api --configuration compileClasspath
~~~

Nếu dependency không có trong graph, điều tra khai báo và resolution. Nếu dependency có nhưng package vẫn không tồn tại, kiểm tra artifact thực tế, source set, package name và module encapsulation nếu dùng JPMS.

## 18. Ví dụ chẩn đoán: task thất bại khi ghi file

Giả sử:

~~~text
Execution failed for task ':app:generateConfig'.
> java.nio.file.AccessDeniedException: ...
~~~

Thông báo chỉ ra task đang thực thi và filesystem từ chối thao tác. Hướng điều tra:

1. Đọc đường dẫn đầy đủ trong exception.
2. Xác định task đang ghi output ở đâu.
3. Kiểm tra user của tiến trình Gradle có quyền ghi thư mục không.
4. Kiểm tra file có đang bị process khác khóa không.
5. Kiểm tra antivirus hoặc policy của CI runner.
6. Kiểm tra task có ghi vào thư mục source hoặc thư mục của project khác không.
7. Kiểm tra output property có trỏ đến vị trí hợp lệ không.

Nếu lỗi chỉ xảy ra trên CI, so sánh user, workspace permission và filesystem của runner với máy local. Không cần thay dependency version nếu exception chỉ rõ vấn đề quyền ghi.

## 19. Configuration cache và lỗi tương thích plugin

Nếu bật configuration cache và build báo không thể lưu hoặc tái sử dụng configuration cache, điều đó không nhất thiết có nghĩa task execution bị lỗi.

Có thể chạy đối chiếu:

~~~shell
./gradlew build --no-configuration-cache
~~~

Nếu build chạy được khi tắt configuration cache nhưng thất bại khi bật, tập trung vào build logic, plugin và task configuration compatibility.

Một số nguyên nhân:

- Plugin truy cập Gradle model theo cách không tương thích.
- Task action giữ hoặc truy cập object configuration không được hỗ trợ.
- Build script sử dụng trạng thái bên ngoài mà configuration cache không thể ghi nhận.
- Custom task không khai báo input/configuration đúng.
- Plugin version cũ chưa hỗ trợ configuration cache đầy đủ.

Tắt configuration cache có thể giúp xác nhận giả thuyết và tiếp tục công việc tạm thời. Để xử lý lâu dài, xem report configuration cache và sửa plugin/build logic liên quan.

Không nhầm lỗi configuration cache với build cache. --no-configuration-cache chỉ tắt cơ chế tái sử dụng configuration result cho lần gọi đó; nó không tắt build cache task output.

## 20. Các tùy chọn chẩn đoán thường dùng

| Lệnh/tùy chọn | Khi nào dùng |
|---|---|
| ./gradlew --version | Xác định Gradle và JVM thực sự được dùng |
| ./gradlew --status | Xem daemon đang hoạt động |
| ./gradlew --stop | Dừng daemon để thử lại với tiến trình mới |
| --stacktrace | Xem exception và nguyên nhân lồng nhau |
| --info | Bổ sung log về configuration, resolution và task |
| --debug | Điều tra sâu khi log thường chưa đủ |
| --dry-run | Xem task graph dự kiến |
| --offline | Xác định build có phụ thuộc vào artifact chưa cache không |
| --refresh-dependencies | Kiểm tra lại trạng thái dependency resolution |
| --no-configuration-cache | So sánh lỗi có liên quan configuration cache không |
| --no-build-cache | So sánh hành vi khi không khôi phục output từ build cache |
| --rerun-tasks | Buộc task được chọn chạy lại thay vì up-to-date |

Ví dụ một lượt chẩn đoán cơ bản:

~~~shell
./gradlew --version
./gradlew :app:build --stacktrace
./gradlew :app:build --info --stacktrace
./gradlew :app:build --dry-run
~~~

Không cần chạy mọi lệnh trong bảng cho mọi lỗi. Chọn lệnh phù hợp với giai đoạn đang nghi ngờ.

## 21. Một quy trình chẩn đoán từ đầu đến cuối

Khi nhận một lỗi Gradle, hãy đi theo trình tự sau.

### Bước 1 — Lưu lại điều kiện tái hiện

Ghi nhận:

- Lệnh chính xác đã chạy.
- Thư mục làm việc/root build.
- Gradle Wrapper version.
- JVM chạy Gradle.
- OS, shell và CI/IDE/container nếu liên quan.
- Commit/source state.
- Lỗi xuất hiện ở local, IDE hay CI.

Không bắt đầu bằng việc thay đổi code; trước tiên cần biết lỗi có thể tái hiện ở đâu.

### Bước 2 — Xác định Gradle đã khởi động chưa

Chạy ./gradlew --version.

- Nếu không chạy được: tập trung Wrapper, JVM, network và Gradle User Home.
- Nếu chạy được: tiếp tục xác định initialization/configuration.

### Bước 3 — Xác định giai đoạn thất bại

Đọc phần What went wrong?, task path và stacktrace.

- Không đọc được settings: initialization.
- Build script/plugin lỗi: configuration.
- Không resolve dependency: resolution.
- Task action/compiler/test/process lỗi: execution.

### Bước 4 — Xác định project và task cụ thể

Dùng task path đầy đủ như :app:compileJava. Nếu cần, xem tasks --all và --dry-run.

### Bước 5 — Tách lỗi dependency khỏi lỗi task

Nếu lỗi nhắc đến configuration như compileClasspath hoặc runtimeClasspath, xem dependency report và dependencyInsight. Nếu compiler đã chạy và đưa ra lỗi source, xem compiler output.

### Bước 6 — Kiểm tra môi trường liên quan

Chỉ kiểm tra các yếu tố phù hợp với exception: JDK, permission, network, disk, process, service hoặc toolchain.

### Bước 7 — Tạo một phép thử nhỏ

Chạy task tối thiểu có thể tái hiện lỗi. Không thay nhiều biến cùng lúc.

### Bước 8 — Xác nhận nguyên nhân và kết quả sửa

Sau khi sửa, chạy lại đúng lệnh đã tái hiện lỗi. Nếu lỗi ban đầu xảy ra trong CI, cần xác nhận trong cùng loại runner hoặc môi trường tương đương.

### Bước 9 — Ghi lại cách phòng ngừa

Nếu lỗi do cấu hình hoặc môi trường không ổn định, ghi rõ yêu cầu JDK, property, repository, credential, toolchain hoặc service để người khác có thể tái hiện build.

## 22. Những nhầm lẫn thường gặp

| Dễ nhầm | Cách hiểu đúng |
|---|---|
| Task có tên compileJava xuất hiện nghĩa lỗi chắc chắn do source | Compile classpath, toolchain hoặc generated source cũng có thể khiến compile task thất bại |
| Mọi lỗi build đều là lỗi code | Wrapper, JVM, settings, plugin, repository và filesystem đều có thể gây lỗi |
| Plugin không tìm thấy là dependency implementation thiếu | Plugin resolution có repository và lifecycle riêng |
| JAVA_HOME quyết định mọi JDK trong build | Gradle JVM, IDE JVM và Java toolchain có thể khác nhau |
| Dependency có trong cache nghĩa build không cần mạng | Metadata/version có thể cần refresh hoặc artifact khác chưa có |
| --stacktrace tự chỉ ra cách sửa | Nó cung cấp exception path; cần đọc root cause và ngữ cảnh |
| Task failure luôn do task action | Resolution hoặc input validation có thể thất bại trước action |
| --dry-run chứng minh task sẽ chạy thành công | Nó chỉ cho biết graph dự kiến, không thực thi logic task |
| --stop sửa lỗi Gradle daemon | Nó chỉ dừng daemon; nguyên nhân có thể vẫn tồn tại |
| Tắt cache giải quyết lỗi build | Chỉ hữu ích khi lỗi liên quan cache behavior; không sửa code hoặc cấu hình sai |
| Lỗi trên CI chắc chắn là do CI | Cần so sánh JDK, property, repository, permission và service giữa môi trường |
| Dòng cuối log là root cause | Nguyên nhân có thể nằm ở exception đầu tiên hoặc một Caused by sâu hơn |

## 23. Bảng tra cứu nhanh

| Muốn xác định... | Bắt đầu từ... |
|---|---|
| Gradle/JVM có khởi động được không? | ./gradlew --version |
| Wrapper tải distribution ở đâu? | gradle-wrapper.properties |
| JVM nào chạy Gradle? | --version, JAVA_HOME, org.gradle.java.home, IDE settings |
| Project nào thuộc build? | settings.gradle(.kts) |
| Plugin được resolve từ đâu? | pluginManagement.repositories |
| Dependency được resolve từ đâu? | repositories, configuration và dependency report |
| Task nào được chọn? | tasks --all, task path, --dry-run |
| Task thất bại vì gì? | --stacktrace, --info, compiler/test/process output |
| File bị từ chối truy cập? | Exception path, permission, file lock |
| Daemon có vấn đề? | --status, --stop, daemon log |
| Lỗi do configuration cache? | Report cache và thử --no-configuration-cache |
| Lỗi do build cache? | Task outcome, --no-build-cache, input/output model |

## 24. Nguyên tắc điều tra

Một thông báo build failure là điểm bắt đầu của việc chẩn đoán. Hãy xác định Gradle đã đi đến giai đoạn nào, project/task nào đang được xử lý và exception đầu tiên có ý nghĩa là gì. Sau đó kiểm tra đúng lớp: môi trường, cấu hình, dependency resolution hoặc task execution.

Khi đã phân loại đúng, phạm vi sửa lỗi thường thu hẹp đáng kể. Lỗi Wrapper/JDK cần kiểm tra tiến trình khởi động; lỗi plugin/settings cần kiểm tra build model; lỗi dependency cần kiểm tra repository và variant; lỗi compile/test/process cần xem input, toolchain và output của task. Cách tiếp cận theo giai đoạn giúp tránh thay đổi nhiều cấu hình không liên quan và giữ được khả năng tái hiện lỗi.
