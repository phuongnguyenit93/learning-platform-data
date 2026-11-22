# Xử lý lỗi encoding, đường dẫn, tài nguyên trùng và mã sinh không ổn định trong Gradle

## 1. Vì sao cùng một dự án Java lại “chạy ở máy A, lỗi ở máy B”?

Một dự án Java/Gradle có thể biên dịch thành công trên laptop nhưng thất bại ở Linux CI, đọc sai tiếng Việt từ file cấu hình, đóng gói JAR có resource khác dự kiến hoặc biên dịch lại liên tục dù không sửa mã. Các triệu chứng tưởng không liên quan này thường có chung nguyên nhân: **build chưa mô tả đầy đủ dữ liệu đầu vào, quy tắc biến đổi và vị trí đầu ra**.

Bốn nhóm lỗi của bài này:

1. **Encoding:** các byte trong source/resource được đọc bằng bảng mã khác với bảng mã đã dùng để ghi; compiler, copy filter, Java runtime hoặc terminal xử lý sai ký tự.
2. **Đường dẫn:** script phụ thuộc working directory, absolute path, đường phân cách, chữ hoa/chữ thường, symlink hoặc thư mục output không thuộc project.
3. **Tài nguyên trùng:** nhiều file đầu vào có **cùng đường dẫn đích** trong `processResources`, `Copy` hay `Jar`; cấu hình tùy ý `EXCLUDE`/`INCLUDE` có thể che mất lỗi.
4. **Mã sinh không ổn định:** generator dùng thời gian hiện tại, random IDs, thứ tự file không xác định, default charset hoặc output chồng lấn; dẫn đến invalidation không cần thiết, artifact hash thay đổi, cache miss hoặc build không lặp lại được.

**Kết quả học tập:** bạn có thể đọc log để phân biệt lỗi thuộc `compileJava`, `processResources`, `jar`, runtime classpath hay custom generator; cấu hình Gradle Groovy DSL và Java 17 chạy được; khai đúng input/output và producer-consumer dependencies; so sánh hai lần clean build để phát hiện đầu ra không tái lập.

Các ví dụ dùng **Gradle Groovy DSL** (`build.gradle`/`settings.gradle`), Java 17, Gradle Wrapper và file nội dung UTF-8. Trên Linux/macOS dùng `./gradlew`; trên Windows PowerShell dùng `.\gradlew.bat`. Một số snippet là **phần mở rộng**, không độc lập; bài lab đầy đủ nằm ở phần 9.

## 2. Xác định đúng pha lỗi trước khi sửa

Gradle Java Application thường có chuỗi công việc:

~~~text
src/main/java/*.java             src/main/resources/*
          |                               |
          v                               v
    compileJava                     processResources
          |                               |
          |        outputs                 |
          +---------+---------------------+
                    v
            classes + resources
                    |
              jar / run
                    |
           Java runtime đọc resource
~~~

Nếu có generated Java:

~~~text
generateGreeting (@Input -> @OutputDirectory)
          |
          +--> generated Java source directory
                    |
                    v
                compileJava
                    |
                classes
~~~

**Phân biệt nơi gây lỗi:**

| Triệu chứng | Kiểm tra trước |
| --- | --- |
| `unmappable character for encoding ...` | `compileJava`, file source bytes, `options.encoding` |
| `illegal character: '\u...'` | Encoding/source BOM hoặc ký tự lạ trong Java source |
| Java compile được nhưng resource hiển thị “ChÃ o” | Cách **Java runtime đọc resource**, `Properties.load`, console encoding |
| `Entry ... is a duplicate but no duplicate handling strategy ...` | `processResources`/`Copy`/`Jar`, paths tương đối sau copy |
| `File not found` trên CI | Path relative/CWD, uppercase vs lowercase, resource classpath |
| JAR có đúng tên file nhưng dữ liệu sai | Resource overwrite, copy filtering, artifact order, generated file stale |
| `compileJava` chạy ở mọi invocation | Inputs/outputs của generator, dynamic version/annotation processing, task implementation |
| Hai lần `clean jar` có checksum khác | Timestamp, file order, generated content, environment/JDK differences |
| `processResources` qua nhưng runtime không thấy file | Sai vị trí resource, `getResourceAsStream` path, packaging |

**Không bắt đầu bằng việc xóa mọi Gradle cache.** Cache cleaning không sửa nguồn encoding sai, path sai hoặc resource bị sao chép hai lần.

## 3. Encoding: nơi nào cần UTF-8 và vì sao một flag không đủ?

“Encoding UTF-8” không phải một nút bật cho toàn bộ pipeline. Có ít nhất bốn biên cần kiểm tra:

~~~text
File .java trên đĩa
   --[javac đọc source bytes]--> class file
File .properties trên đĩa
   --[Gradle Copy/filter đọc và ghi]--> build/resources/main
   --[JAR đóng gói bytes]--> classpath resource
   --[Java Properties/Reader giải mã]--> String trong ứng dụng
   --[System.out và terminal]--> ký tự người dùng nhìn thấy
~~~

| Vị trí | Cấu hình đúng | Điều **không** được giải quyết |
| --- | --- | --- |
| Java source | `JavaCompile.options.encoding = 'UTF-8'` | Không tự chuyển file đang lưu bằng Windows-1258 thành UTF-8 |
| Resource filtering | `Copy.filteringCharset = 'UTF-8'` | Không tự thay đổi cách Java đọc resources sau khi đóng gói |
| Java đọc text resource | `InputStreamReader(..., UTF_8)` hoặc `Files.readString(path, UTF_8)` | Không làm compiler chọn encoding khác |
| Java `Properties` | `Properties.load(Reader)` với UTF-8 | `Properties.load(InputStream)` vẫn có semantics Latin-1 |
| Terminal/stdout | Terminal/JVM output encoding và font tương thích | Không sửa bytes bị hỏng trong source/JAR từ trước |

### 3.1. `JavaCompile.options.encoding`

Trong `build.gradle` với Java plugin:

~~~groovy
plugins {
    id 'java'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Cách này áp cho `compileJava` và `compileTestJava` cùng những `JavaCompile` task được đăng ký thêm sau. `configureEach` giữ task configuration lazy.

**Điều kiện:** Java source thật sự được lưu bằng UTF-8. Nếu file đã có bytes không hợp lệ cho UTF-8, sửa nguồn bằng editor hoặc chuyển encoding có kiểm soát; không “chữa” bằng việc thay `options.encoding` tùy ý theo máy.

Ví dụ khi tự biên dịch Java 17 bằng `javac`:

~~~bash
javac -encoding UTF-8 --release 17 -d out src/main/java/demo/Main.java
java -cp out demo.Main
~~~

`-encoding UTF-8` chọn **charset của source**; `--release 17` giới hạn ngôn ngữ/bytecode và Java SE APIs; đây là **hai** chức năng khác nhau.

### 3.2. Không nhầm `options.release` với encoding

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
~~~

- **Toolchain** chọn `javac`/launcher JDK 17.
- **Encoding** chọn cách đọc `.java`.
- **Release** chọn Java language/API target 17.

Chỉ đặt `options.release=17` không sửa được `unmappable character`, và chỉ đặt `options.encoding='UTF-8'` không buộc compiler dùng JDK 17.

### 3.3. Resource binary không phải text

`src/main/resources` có thể chứa PNG, JKS, ZIP, PDF, fonts, ảnh hay binary metadata. `processResources` mặc định **copy bytes**; khi bạn thêm `expand`/`filter`, copy task cần giải mã và ghi lại các text resources.

**Sai:** áp `filter { ... }` hoặc `expand(...)` toàn bộ resources tree, gồm PNG/ZIP. Những byte không phải text có thể bị hỏng khi đi qua text transform.

**Đúng:** chỉ filter một tập file văn bản đã biết:

~~~groovy
tasks.named('processResources', Copy) {
    filteringCharset = 'UTF-8'
    filesMatching('config/app.properties') {
        expand(appVersion: '1.0.0')
    }
}
~~~

Đoạn này là snippet cho project Java có file `src/main/resources/config/app.properties`. `expand` nhận Groovy template placeholders, ví dụ `app.version=${appVersion}`. Không cần filter những resources khác.

**Lưu ý:** `expand` đánh giá các biểu thức template; với nội dung nhận từ nguồn không tin cậy, nên dùng cơ chế substitution giới hạn và escape thay vì cho phép expression tùy ý. Cần theo dõi input data của templates bằng task inputs.

### 3.4. `Properties.load(InputStream)`: bẫy kinh điển

Java API `java.util.Properties.load(InputStream)` đọc theo quy tắc **ISO-8859-1/Latin-1** với Unicode escapes; không tự hiểu rằng file của bạn được lưu UTF-8.

**Sai về mặt encoding nếu file có UTF-8 Unicode trực tiếp:**

~~~java
Properties p = new Properties();
try (InputStream in = Main.class.getResourceAsStream("/config/app.properties")) {
    p.load(in);
}
~~~

Để giữ tiếng Việt UTF-8, dùng `Reader` rõ charset:

~~~java
Properties p = new Properties();
try (InputStream in = Main.class.getResourceAsStream("/config/app.properties")) {
    if (in == null) {
        throw new IllegalStateException("Missing resource");
    }
    try (Reader reader = new InputStreamReader(in, StandardCharsets.UTF_8)) {
        p.load(reader);
    }
}
~~~

Trong Java, `Properties.load(Reader)` đọc characters do `Reader` cung cấp, nên bản lab phần 9 sẽ hiển thị tiếng Việt đúng. `ResourceBundle` trên Java hiện đại có quy tắc charset riêng; không suy diễn từ nó sang `Properties.load(InputStream)`.

### 3.5. Terminal có thể sai dù source, resource và class đúng

Nếu log có mojibake nhưng unit test so sánh Java strings đúng, kiểm tra **output encoding của terminal**. Trên Windows, code page/cấu hình console/JVM có thể khác UTF-8. Trên Linux/macOS kiểm tra locale tương ứng. Thay terminal/font/encoding cần có căn cứ; tránh chuyển toàn bộ source sang một legacy charset chỉ vì một console hiển thị sai.

### 3.6. CRLF, LF và BOM

- Windows editor có thể dùng CRLF, Linux thường dùng LF; Git có thể chuyển newline theo `.gitattributes`.
- UTF-8 BOM ở đầu Java source có thể bị javac xem là ký tự không mong muốn tùy tool/phiên bản. Hãy lưu Java source **UTF-8 không BOM** để dễ tái lập.
- Nếu generator viết file với `System.lineSeparator()`, output bytes có thể khác Windows/Linux.
- Chọn **LF** cho generated text nếu bản định dạng yêu cầu byte-for-byte reproducibility.
- Với file properties/text, kiểm tra cả **bytes gốc** lẫn cách consumer giải mã; một flag Gradle không sửa tất cả các biên.

## 4. Đường dẫn: quy tắc project-relative và không phụ thuộc CWD

Đường dẫn file là điểm khác biệt rất lớn giữa local, CI, Windows, Linux và multi-project builds.

### 4.1. Những cách thường sai

~~~groovy
def input = new File('src/main/resources/config/app.properties')
def output = new File('build/generated/example.txt')
def other = new File('C:\\Users\\somebody\\jdk\\lib')
~~~

**Vấn đề:**
- `new File('relative/path')` dùng **current working directory** của tiến trình, không bảo đảm là `projectDir` của subproject.
- `build/generated` bị hard-code, không dùng Provider của `layout.buildDirectory`.
- Path `C:\Users\...` gắn với máy một người, phá CI/Unix.
- Script có thể trỏ nhầm root project khi thực ra đang chạy `:module:generate` từ multi-project.
- Hard-code đường phân cách `/` hoặc `\\` trong string nội bộ có thể gây lỗi khi chuyển OS.

### 4.2. API Gradle khuyên dùng

~~~groovy
def configFile = layout.projectDirectory.file('config/app.properties')
def targetDir = layout.buildDirectory.dir('generated/config')
~~~

- `layout.projectDirectory.file(...)` trả một `RegularFile` nằm tương đối theo project.
- `layout.buildDirectory.dir(...)` trả `Provider<Directory>`, thích hợp làm task output.
- `file('...')` trong Gradle Project DSL cũng resolve path tương đối theo project, nhưng Providers/typed file properties giúp lazy tracking tốt hơn.
- `project.layout.settingsDirectory` không phải thuộc tính Project Layout mặc định như `projectDirectory`; đừng đoán API. Nếu cần root project layout, cân nhắc thiết kế explicit input/path trong convention plugin.

### 4.3. CWD của Java runtime cũng là một vấn đề khác

**Dễ sai:**

~~~java
Path input = Path.of("src/main/resources/config/app.properties");
String text = Files.readString(input, StandardCharsets.UTF_8);
~~~

Đoạn này phụ thuộc **working directory của process Java**. Khi chạy `gradlew run` từ project, nó có thể tình cờ đúng, nhưng khi đóng JAR và chạy bằng `java -jar` ở folder khác thì resource source path không còn.

**Tốt hơn nếu file là classpath resource:**

~~~java
try (InputStream in =
        Main.class.getResourceAsStream("/config/app.properties")) {
    if (in == null) {
        throw new IllegalStateException("Missing classpath resource");
    }
    // đọc qua InputStreamReader(..., UTF_8)
}
~~~

Classpath resource là tài sản **được đóng gói**, không phải đường dẫn source tree. Dấu `/` đầu tiên ở `Class.getResourceAsStream` nghĩa là tra từ **classpath root**; tên path trong JAR phân tách bằng `/` trên mọi OS.

### 4.4. Case sensitivity và tên file

Một file thực tế ở:

~~~text
src/main/java/demo/Main.java
~~~

phải tương thích:

~~~java
package demo;
public class Main { }
~~~

Trên hệ thống file case-insensitive, `Main.java` và `main.java` có thể được xem như cùng tên; trên nhiều Linux CI filesystems chúng khác nhau. Tương tự `/Config/App.properties` không bằng `/config/app.properties` nếu build/run ở case-sensitive filesystem.

Đặt tên file, directory và resource references **khớp chính xác chữ hoa/chữ thường**, kiểm tra Git tracked file names, đặc biệt sau một lần rename chỉ thay đổi chữ hoa trên Windows/macOS.

### 4.5. Symlink, relative paths và CI security

- Symlink có thể trỏ ra ngoài workspace mà local vẫn truy cập được, còn CI container không có target.
- Dùng `../shared` để truy cập module khác phải có chủ ý và khai input hợp lệ; không tùy tiện viết ra thư mục chung.
- Không lấy path từ untrusted user input rồi nối trực tiếp vào output root nếu chưa validate traversal (`..`) hoặc absolute paths.
- Đối với custom task, dùng `DirectoryProperty`/`RegularFileProperty` giúp mô tả nguồn/đích rõ và cho Gradle theo dõi.

## 5. Tài nguyên trùng: hiểu thế nào là cùng destination path

`processResources` là task kiểu `ProcessResources` có behavior của `Copy`. Các resources theo mặc định từ `src/main/resources` được copy sang một output resource directory như `build/resources/main`.

Nếu hai nguồn khác nhau cùng sinh file:

~~~text
src/main/resources/config/app.properties
generated/resources/config/app.properties
                      |
                      v
             build/resources/main/config/app.properties
~~~

cả hai cùng muốn chiếm **relative destination path `config/app.properties`**. Đây là **duplicate resource**, dù absolute source paths khác nhau.

Tương tự, `Jar` có thể nhận hai entries `META-INF/services/com.example.Service` từ các nguồn khác nhau khi bạn đang tạo fat/uber JAR.

### 5.1. `DuplicatesStrategy`: năm giá trị

| Giá trị | Khi destination path bị trùng |
| --- | --- |
| `DuplicatesStrategy.FAIL` | Ném `DuplicateFileCopyingException`, dừng task. Phù hợp để phát hiện lỗi/không rõ owner |
| `DuplicatesStrategy.EXCLUDE` | Giữ entry **đầu tiên** theo thứ tự copy mà task thực sự duyệt, bỏ những entry sau |
| `DuplicatesStrategy.INCLUDE` | Không ngăn trùng; ZIP/JAR có thể chứa nhiều entries cùng tên, directory copy có thể bị ghi đè |
| `DuplicatesStrategy.WARN` | Ghi warning nhưng hành vi copy giống `INCLUDE` |
| `DuplicatesStrategy.INHERIT` | Kế thừa chiến lược từ parent CopySpec; là default ở mức descriptor |

**Điểm quan trọng:** `INHERIT` không được hiểu là “luôn FAIL” hoặc “luôn EXCLUDE” trên mọi task/Gradle version. Nếu không có policy cuối cùng được đặt, Gradle có thể báo lỗi yêu cầu chỉ rõ handling strategy. Để có behavior đáng dự đoán, **khai chiến lược ở nơi sở hữu copy operation**.

### 5.2. Fail-fast cho resources

~~~groovy
import org.gradle.api.file.DuplicatesStrategy

tasks.named('processResources', Copy) {
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
~~~

Nếu có hai files cùng relative destination path, task thất bại thay vì âm thầm chọn một. Đây thường là default **policy tốt cho production build** khi không có yêu cầu merge.

**Đừng chuyển ngay sang `EXCLUDE` chỉ để build xanh.** Điều đó có thể làm resource phiên bản cũ hoặc môi trường không mong muốn thắng, dẫn đến lỗi runtime khó phát hiện.

### 5.3. Demo tạo xung đột có chủ đích

Tạo hai thư mục:

~~~text
duplicates-lab/
├── srcA/config/feature.properties
├── srcB/config/feature.properties
└── build.gradle
~~~

Cả hai file có relative path `config/feature.properties`. Thêm task:

~~~groovy
plugins {
    id 'base'
}

tasks.register('copyDuplicateResources', Copy) {
    from 'srcA'
    from 'srcB'
    into layout.buildDirectory.dir('duplicate-demo')
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
~~~

Chạy:

~~~bash
./gradlew copyDuplicateResources
~~~

**Kết quả kỳ vọng:** task báo duplicate path và **FAILED**, không có stdout lỗi chính xác chung cho mọi Gradle version. Để giải quyết đúng, bạn phải quyết định **source nào được phép sở hữu `config/feature.properties`** hoặc đặt lại đích để tránh conflict.

### 5.4. Giải pháp ưu tiên: định rõ ownership và destination

Nếu source A là config chung, source B là config dành riêng cho một profile, không đặt cả hai vào cùng destination path:

~~~groovy
tasks.register('copyProfiles', Copy) {
    from('srcA') {
        into 'common'
    }
    from('srcB') {
        into 'profiles'
    }
    into layout.buildDirectory.dir('profile-resources')
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
~~~

**Output tương ứng:**

~~~text
build/profile-resources/common/config/feature.properties
build/profile-resources/profiles/config/feature.properties
~~~

Đây là hai paths khác nhau. Nếu hệ thống thật yêu cầu chỉ một file có tên `config/feature.properties`, hãy chọn nguồn theo input/configuration rõ ràng, đừng dựa trên thứ tự copy ngẫu nhiên.

### 5.5. Nếu thực sự cần merge `META-INF/services/*`

Trong JAR với Java ServiceLoader, mỗi file `META-INF/services/<interface-name>` chứa tên implementation classes. Hai libraries có thể cùng có một service descriptor path nhưng chứa các dòng khác nhau. `EXCLUDE` sẽ bỏ implementation của library thứ hai; `INCLUDE` có thể tạo JAR entries trùng mà một số readers xử lý khác nhau.

Nếu đang tạo **fat/uber JAR**, cần **merge nội dung service files** bằng plugin/logic chuyên dụng có semantics rõ. Shadow plugin có hỗ trợ `mergeServiceFiles()` khi cấu hình đúng (plugin ngoài, không có sẵn trong Java core). Không áp `mergeServiceFiles` vào project chưa dùng Shadow plugin.

**Phân biệt:** JAR thông thường chứa output project và các dependencies nằm **trên classpath riêng**; Java plugin `jar` mặc định không tự unpack tất cả dependency JARs. Resource collisions giữa dependencies chỉ thành collisions trong cùng archive khi có thao tác flatten/unzip/merge rõ ràng.

## 6. `processResources`: copy text và binary đúng cách

`src/main/resources` thường là root tài nguyên của source set `main`. `processResources` copy chúng để classpath runtime thấy được.

### 6.1. Lọc một template UTF-8 cụ thể

Giả sử:

~~~text
src/main/resources/config/app.properties
~~~

Nội dung:

~~~properties
app.version=${appVersion}
app.greeting=Chào từ tài nguyên UTF-8
~~~

`build.gradle` snippet:

~~~groovy
version = '1.0.0'
def stableVersion = version.toString()

tasks.named('processResources', Copy) {
    duplicatesStrategy = DuplicatesStrategy.FAIL
    filteringCharset = 'UTF-8'

    inputs.property('appVersion', stableVersion)
    filesMatching('config/app.properties') {
        expand(appVersion: stableVersion)
    }
}
~~~

Sau khi copy/expand, file ở output có:

~~~properties
app.version=1.0.0
app.greeting=Chào từ tài nguyên UTF-8
~~~

Bài lab phần 9 sẽ sử dụng đúng pattern này.

**Vì sao phải khai `inputs.property`?** `appVersion` là dữ liệu ảnh hưởng output của task. Nếu version thay đổi, Gradle cần biết input thay đổi để không giữ output cũ `UP-TO-DATE`. Với tính năng filtering, cách theo dõi inputs có thể khác theo plugin/API; khai rõ property dễ audit và tránh logic phụ thuộc biến bên ngoài không được theo dõi.

### 6.2. Dùng `filesMatching` thay vì filter toàn bộ tree

Không dùng:

~~~groovy
tasks.named('processResources', Copy) {
    expand(appVersion: '1.0.0')
}
~~~

nếu `src/main/resources` chứa PNG/ZIP/JKS; code này có thể ép **mọi resource** qua template filter. Đặt trong `filesMatching('config/app.properties')` để chỉ biến đổi text file có chủ đích.

### 6.3. Dùng filter line-based khi không cần template expressions

Một cách thay token rõ ràng:

~~~groovy
tasks.named('processResources', Copy) {
    filteringCharset = 'UTF-8'
    filesMatching('config/app.properties') {
        filter { String line ->
            line.replace('@APP_VERSION@', '1.0.0')
        }
    }
}
~~~

Đây là snippet thay thế cho `expand`, dùng khi source có token `@APP_VERSION@`. Với Gradle 10 trở đi, một số Ant FilterReader classes không còn tự có trên build script classpath; **closure-based `filter`** như ở trên không cần Ant filter class. Không phối hợp hai cú pháp placeholder khác nhau trong cùng template trừ khi chủ động.

### 6.4. Đừng ghi vào `src/main/resources` khi process

**Sai:**

~~~groovy
tasks.named('processResources', Copy) {
    doFirst {
        file('src/main/resources/config/app.properties').text = 'new content'
    }
}
~~~

Đây là side effect làm thay đổi source tree trước Copy, có thể làm Git dirty, làm build không thể tái lập, hoặc gây race khi chạy nhiều project/task.

**Đúng:** nguồn trong `src/main/resources` là input bất biến; biến đổi/copy sang output dưới `layout.buildDirectory`. Nếu resource được generate, dùng một generator task riêng có declared inputs/outputs và nối output của nó vào `processResources`.

## 7. Mã sinh không ổn định: năm nguồn gây non-determinism

Generated code thường do annotation processors, OpenAPI/protobuf generators, resource template tasks hoặc custom Gradle tasks tạo ra. Một generated file nên là **hàm xác định của inputs**.

~~~text
Output = f(nguồn, config, generator version, toolchain, declared environment)
~~~

Nếu cùng inputs mà output thay đổi mỗi lần chạy, Gradle khó dùng incremental build/build cache đúng nghĩa. Các nguyên nhân điển hình:

| Nguyên nhân | Ví dụ dễ sai | Cách thiết kế lại |
| --- | --- | --- |
| Thời gian hiện tại | `Instant.now()` ghi vào header generated Java | Bỏ timestamp; nếu cần build ID, nhận một version input cố định |
| Random IDs | `UUID.randomUUID()` hoặc random suffix | Dựa trên tọa độ/module/hash có quy tắc ổn định |
| Thứ tự không cố định | `File.listFiles()` rồi ghi theo iteration | Sort theo relative path/identifier đã normalize |
| Encoding/newline mặc định | `File.text = ...`/`System.lineSeparator()` | Ghi `UTF-8` với `\n` cố định |
| Absolute paths/hostnames | Ghi `/home/ci/...` hoặc `C:\...` vào generated source | Dùng relative paths/normalized logical identifiers |
| Inputs thiếu | Task dùng env var không khai `@Input` | Đưa vào `Property`/`Provider` được khai là input |
| Outputs chồng lấn | Hai generators viết cùng `build/generated` | Mỗi task sở hữu output directory riêng |
| Generator version không khóa | Plugin generator dùng dynamic version | Pin generator/plugin version, test kết quả |
| Java toolchain tùy máy | Local JDK 17, CI JDK 21 với codegen dựa vào JDK API | Toolchain/policy rõ và test target |
| Mã sinh vào `src/main/java` | Task mutate tracked source files | Sinh vào `build/generated/sources/<task>/...` |

### 7.1. Không dùng timestamps làm “đảm bảo rebuild”

**Sai:**

~~~groovy
tasks.register('generateVersion') {
    doLast {
        def out = file('src/main/java/demo/BuildInfo.java')
        out.text = "// generated at " + new Date() + "\n"
    }
}
~~~

- Không khai inputs/outputs.
- Sửa source tree trực tiếp.
- Output thay đổi theo thời gian dù code/config không đổi.
- Task action phụ thuộc `project.file(...)`, gây rắc rối với configuration cache và build reproducibility.
- Có thể khiến `compileJava`/IDE chạy lại liên tục.

Muốn có provenance của release artifact, hãy dùng **version, commit hash đã kiểm soát và được khai làm input** trong một tài liệu metadata riêng, không tự chèn time/random vào mỗi Java source.

### 7.2. Output directory phải có chủ sở hữu rõ

Đặt:

~~~text
build/generated/sources/greeting/java/
build/generated/sources/openapi/java/
build/generated/resources/build-info/
~~~

Mỗi generator chỉ sở hữu output riêng. Nếu hai tasks cùng ghi `build/generated/sources` không phân chia, Gradle có thể không suy luận dependencies/races đúng như bạn mong muốn và cache outputs có thể chứa file của task khác.

**Nguyên tắc:** Task B tiêu thụ output Task A qua **task provider / output property** có task dependency metadata, không phải đoán một path string rồi hy vọng A đã chạy.

### 7.3. Input annotation quyết định up-to-date checks

Custom task type lý tưởng có:
- `@Input Property<String>`, `@InputFile RegularFileProperty`, `@InputFiles ConfigurableFileCollection` khi cần.
- `@OutputDirectory DirectoryProperty` hoặc `@OutputFile RegularFileProperty`.
- `@PathSensitive(PathSensitivity.RELATIVE)` với file inputs cần cache portability.
- `@TaskAction` chỉ làm công việc thực sự khi task chạy.
- `TaskProvider` để nối generator và consumer.

Các annotations giúp Gradle fingerprint inputs/outputs. Nếu **một giá trị ảnh hưởng output nhưng không được khai input**, Gradle có thể báo `UP-TO-DATE` sai và giữ artifact cũ. Nếu **input không cần thiết** được khai vào task, một thay đổi vô hại lại kích hoạt rebuild.

### 7.4. `UP-TO-DATE`, `FROM-CACHE` và reproducibility

| Trạng thái | Nghĩa |
| --- | --- |
| `UP-TO-DATE` | Với cùng task và trạng thái local, inputs/outputs được xem không đổi |
| `FROM-CACHE` | Task outputs được khôi phục từ build cache khi task cacheable và key khớp |
| Task thực sự chạy | Input/output/implementation thay đổi hoặc task được forced rerun |
| `NO-SOURCE` | Source task không có source inputs để xử lý |
| `SKIPPED` | Task bị bỏ qua theo rule/condition hoặc lý do khác |

**Không hiểu** rằng một task `UP-TO-DATE` chứng minh artifact byte-for-byte reproducible trên máy khác. Reproducibility cần **hai independent builds với cùng input/policy** cho outputs như nhau; up-to-date chỉ là cơ chế bỏ qua task khi local state được xem tương đương.

## 8. Annotation processing và generated sources từ plugin

Java annotation processors thường chạy như một phần của `compileJava` khi khai đúng configuration:

~~~groovy
dependencies {
    annotationProcessor 'com.example:processor:1.0'
    compileOnly 'com.example:annotations:1.0'
}
~~~

Đây là **snippet minh họa với tọa độ giả định**, không runnable nếu repository không có artifacts. `annotationProcessor` xác định processor path; `compileOnly` cho annotation APIs khi compile mà không thêm runtime dependency mặc định.

### 8.1. Không thêm processor vừa `implementation` vừa `annotationProcessor` tùy tiện

Gradle Java plugin tách processor path khỏi compile classpath. Nếu một thư viện processor cần chạy khi compile, phải đặt nó ở configuration phù hợp thay vì dựa vào classpath scanning ngầm. Việc sửa sai có thể khiến task không generate hoặc tạo ra graph khác khi CI chạy.

### 8.2. Processor generated files do compiler sở hữu

Với annotation processing tích hợp trong `JavaCompile`, Gradle/compiler quản lý generated source location (theo compiler/plugin). Không tự đồng thời thêm cùng folder generated source vào `sourceSets.main.java.srcDirs` nếu compiler đã compile các sources do processor tạo; dễ gây double compilation/duplicate class.

### 8.3. Khi dùng external generator task

Với OpenAPI, protobuf hoặc custom codegen plugin:
- Dùng **task** do plugin cung cấp, không chạy generator bằng `Exec` ở top-level configuration.
- Khai đúng generator version/schema/template/flags dưới dạng inputs.
- Đặt generated sources dưới build directory, task-unique location.
- Nối task producer vào source set/compile task bằng provider hoặc task output property.
- Nếu generator không incremental-safe, không ép bật cache chỉ để nhanh.

**Cảnh báo:** Generator plugin có quy tắc task/outputs riêng; đừng ghi đè generated output directory tùy ý nếu plugin đã thiết lập path conventions.

## 9. Bài thực hành Java 17 hoàn chỉnh: UTF-8, resource template và mã sinh ổn định

Ví dụ này cố ý:
- Có source Java và resource **chứa tiếng Việt UTF-8**.
- Có generated Java class với **nội dung xác định** từ một `@Input` string.
- Có **output directory** riêng dưới `build/generated/sources/greeting/java`.
- Nối source set Java tới **TaskProvider** của generator để Gradle suy luận task dependency.
- Chỉ filter một text resource và dùng `filteringCharset='UTF-8'`.
- `processResources` dùng `DuplicatesStrategy.FAIL` để không che xung đột.
- Java runtime dùng `Properties.load(Reader)` với UTF-8.
- Có stdout dự đoán được.

### 9.1. Cấu trúc thư mục

~~~text
stable-build-lab/
├── settings.gradle
├── build.gradle
├── src/
│   └── main/
│       ├── java/
│       │   └── demo/
│       │       └── Main.java
│       └── resources/
│           └── config/
│               └── app.properties
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
~~~

Nếu chưa có Gradle Wrapper, dùng một Gradle đã cài tương thích Java 17 để chạy `gradle wrapper` rồi lưu Wrapper vào repository. Cần có JDK 17 (hoặc Java toolchain resolver phù hợp). Bài lab không cần external Maven library.

### 9.2. `settings.gradle`

~~~groovy
rootProject.name = 'stable-build-lab'
~~~

### 9.3. `build.gradle` — toàn bộ file

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.DuplicatesStrategy
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id 'application'
}

version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.Main'
}

// Đây là task type nhỏ, có inputs/outputs rõ.
abstract class GenerateGreeting extends DefaultTask {
    @Input
    abstract Property<String> getMessage()

    @OutputDirectory
    abstract DirectoryProperty getDestinationDirectory()

    @TaskAction
    void generate() {
        File output = new File(
            destinationDirectory.get().asFile,
            'demo/generated/GeneratedGreeting.java'
        )
        output.parentFile.mkdirs()

        // Escape thành Java String literal hợp lệ.
        String escaped = message.get()
            .replace('\\', '\\\\')
            .replace('"', '\\"')
            .replace('\r', '\\r')
            .replace('\n', '\\n')

        // Nội dung cố định, không timestamp/random/absolute path.
        String source = """package demo.generated;
public final class GeneratedGreeting {
    private GeneratedGreeting() { }
    public static String text() {
        return "${escaped}";
    }
}
"""
        output.setText(source, 'UTF-8')
    }
}

def generatedGreeting = tasks.register(
    'generateGreeting',
    GenerateGreeting
) {
    message.set('Xin chào từ mã sinh')
    destinationDirectory.set(
        layout.buildDirectory.dir('generated/sources/greeting/java')
    )
}

// Nối task provider, không chỉ hard-code path string.
sourceSets {
    main {
        java.srcDir(generatedGreeting)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}

def stableVersion = version.toString()

tasks.named('processResources', Copy) {
    duplicatesStrategy = DuplicatesStrategy.FAIL
    filteringCharset = 'UTF-8'

    // Biến được expand có ảnh hưởng đến output.
    inputs.property('appVersion', stableVersion)

    // Không filter PNG, ZIP, JKS hoặc resources khác.
    filesMatching('config/app.properties') {
        expand(appVersion: stableVersion)
    }
}

tasks.named('jar', Jar) {
    // Tường minh cho Gradle versions cũ hơn 9.0.
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

**Giải thích từng mảnh:**

- `GenerateGreeting` là custom `DefaultTask` type có `@Input Property<String>` và `@OutputDirectory DirectoryProperty`. Gradle có thể fingerprint message và output.
- `@TaskAction` chỉ chạy khi task thực sự được thực thi. Nó không tạo file trong configuration phase.
- File generated có package `demo.generated` và đường dẫn `demo/generated/GeneratedGreeting.java` tương ứng.
- `output.setText(source, 'UTF-8')` tránh dùng JVM default charset.
- Mã sinh có newline cố định và không gọi `Instant.now()` hay `UUID.randomUUID()`.
- `sourceSets.main.java.srcDir(generatedGreeting)` đưa **task output directory** vào source set và cho Gradle biết dependency producer-consumer. Không cần thêm `compileJava.dependsOn('generateGreeting')` thủ công trong mẫu này.
- `options.encoding` bảo đảm javac hiểu tiếng Việt trong cả source viết tay và generated Java.
- `processResources` xử lý đúng file `config/app.properties`; `inputs.property` theo dõi version dùng trong template.
- `DuplicatesStrategy.FAIL` báo lỗi khi hai nguồn copy có cùng destination resource path.
- `jar` cấu hình thứ tự entries/timestamps reproducible. Từ Gradle **9.0** các thiết lập này đã là default cho archives trong những hoàn cảnh được tài liệu mô tả; viết rõ ở đây giúp người đọc hiểu ý định và hỗ trợ các bản Gradle trước đó.

**Giới hạn kỹ thuật:** Task generator dùng output directory riêng. Nếu sau này đổi generator tạo **nhiều tên file khác nhau**, cần có chính sách cleanup outputs cũ trong directory riêng của task; `@OutputDirectory` không phải bảo đảm tự động mọi file cũ biến mất trong mọi tình huống. Không cho task khác ghi vào cùng destination directory.

### 9.4. `src/main/resources/config/app.properties`

**Lưu file bằng UTF-8**, với nội dung chính xác:

~~~properties
app.version=${appVersion}
app.greeting=Chào từ tài nguyên UTF-8
~~~

Sau `processResources`, placeholder được thay thành version:

~~~properties
app.version=1.0.0
app.greeting=Chào từ tài nguyên UTF-8
~~~

Không đặt thêm một file thứ hai có cùng đường dẫn `config/app.properties` ở source root khác khi chưa có chính sách merge rõ.

### 9.5. `src/main/java/demo/Main.java`

~~~java
package demo;

import demo.generated.GeneratedGreeting;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws Exception {
        Properties p = new Properties();

        try (InputStream input =
                 Main.class.getResourceAsStream("/config/app.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                    "Missing /config/app.properties"
                );
            }
            try (Reader reader =
                     new InputStreamReader(input, StandardCharsets.UTF_8)) {
                p.load(reader);
            }
        }

        System.out.println(GeneratedGreeting.text());
        System.out.println(p.getProperty("app.greeting"));
        System.out.println("Version: " + p.getProperty("app.version"));
    }
}
~~~

**Chú ý:**
- `GeneratedGreeting` là class do task tạo, không viết tay trong `src/main/java`.
- `Properties.load(Reader)` đọc các ký tự đã được `UTF-8` decoder chuyển đổi.
- `getResourceAsStream("/config/app.properties")` đọc **classpath resource**, chạy được khi Gradle `run` dùng classes/resources directories. Nó cũng phù hợp khi tài nguyên được đóng gói vào JAR và classpath được thiết lập đúng.
- Sử dụng UTF-8 không phụ thuộc `user.dir` hay đường dẫn `src/main/resources` ở runtime.

### 9.6. Chạy bài thực hành

~~~bash
./gradlew clean run --quiet
~~~

**Stdout chính xác từ chương trình Java (ngoài log Gradle/toolchain khi có):**

~~~text
Xin chào từ mã sinh
Chào từ tài nguyên UTF-8
Version: 1.0.0
~~~

Dòng một đến từ source Java do Gradle task generate; dòng hai đến từ `.properties` với UTF-8; dòng ba đến từ `expand(appVersion: stableVersion)`.

Nếu terminal Windows hiển thị ký tự không đúng nhưng app test/debug strings có nội dung chính xác, kiểm tra terminal encoding/font trước khi thay đổi source file encoding.

### 9.7. Kiểm tra generated file, copied resource và classes

Chạy:

~~~bash
./gradlew generateGreeting processResources compileJava --info
./gradlew run --info
./gradlew jar
~~~

Vị trí kết quả theo cấu hình lab:

~~~text
build/generated/sources/greeting/java/demo/generated/GeneratedGreeting.java
build/resources/main/config/app.properties
build/classes/java/main/demo/Main.class
build/classes/java/main/demo/generated/GeneratedGreeting.class
build/libs/stable-build-lab-1.0.0.jar
~~~

Gradle `compileJava` có thể dùng incremental compilation và task status thay đổi tùy lần chạy. Việc task `generateGreeting` được đưa vào compile source set có nghĩa Gradle biết phải generate file trước khi compile, không dựa vào thứ tự shell chạy.

### 9.8. Kiểm chứng up-to-date

Sau khi chạy một lần, thử:

~~~bash
./gradlew run --info
./gradlew compileJava --info
~~~

Với các inputs và outputs không đổi, Gradle thường đánh dấu `generateGreeting`/`compileJava`/`processResources` là `UP-TO-DATE` trong những trường hợp phù hợp. Task `run` kiểu `JavaExec` vẫn có thể chạy vì nó thực thi chương trình, không mặc nhiên là task có outputs cacheable như `JavaCompile`.

Để kiểm tra generator không phụ thuộc thời gian:

~~~bash
./gradlew generateGreeting --rerun-tasks
./gradlew generateGreeting --rerun-tasks
~~~

So sánh **bytes** file `GeneratedGreeting.java` giữa hai lần: chúng phải giống nhau nếu message/tool version không đổi. Không chỉ nhìn mtime, vì file được ghi lại có thể có timestamp filesystem mới mặc dù nội dung bytes không đổi.

## 10. Bài tập lỗi có chủ đích: quan sát trước–sau

### 10.1. Lỗi encoding của compiler

1. Giữ source `Main.java` chứa tiếng Việt hoặc thêm một Java string `"Tiếng Việt"`.
2. Tạm thay `options.encoding = 'UTF-8'` bằng một charset không phù hợp và chạy `compileJava`.
3. Quan sát lỗi/mis-decoding (tùy bytes/charset, có thể là compile error hoặc string bị sai ở runtime).
4. Khôi phục `UTF-8` và chạy lại.

**Đừng sửa nguồn gốc sang legacy charset** chỉ để bài lab lỗi đúng một thông báo; mục tiêu là hiểu cơ chế encoding. Kết quả cụ thể thay đổi theo compiler và charset.

### 10.2. Lỗi resource encoding của Java runtime

Trong `Main.java`, thay đoạn:

~~~java
try (Reader reader =
         new InputStreamReader(input, StandardCharsets.UTF_8)) {
    p.load(reader);
}
~~~

bằng:

~~~java
p.load(input);
~~~

Khi `app.greeting` có tiếng Việt UTF-8, `Properties.load(InputStream)` giải mã theo Latin-1 và sẽ cho chuỗi sai. Khôi phục `InputStreamReader(..., UTF_8)` để sửa đúng biên lỗi.

### 10.3. Lỗi duplicate resource

Tạo thêm:

~~~text
extra-resources/config/app.properties
~~~

với nội dung bất kỳ rồi thêm trong `build.gradle`:

~~~groovy
sourceSets {
    main {
        resources.srcDir('extra-resources')
    }
}
~~~

Chạy:

~~~bash
./gradlew processResources
~~~

**Kết quả kỳ vọng:** Vì hai files có cùng target path `config/app.properties` và task cấu hình `DuplicatesStrategy.FAIL`, `processResources` báo duplicate và thất bại. Xóa cấu hình thêm source dir hoặc đổi tên/resource ownership đúng để sửa.

**Không** chuyển toàn build sang `duplicatesStrategy=EXCLUDE` để “ẩn” bản thứ hai. Nếu thứ tự files thay đổi, bạn có thể vô tình đóng gói nội dung không mong đợi.

### 10.4. Lỗi non-deterministic generated code

Chèn vào generator:

~~~groovy
String source = "// generated at " + new Date() + "\n" + source
~~~

Đây là snippet minh họa một **sửa sai có chủ đích**: mỗi lần task thực sự chạy, cùng inputs có thể tạo output bytes khác nhau. Nếu còn dùng `@Input` message như cũ, Gradle **không biết clock time là input**, nên:
- Lần thường task có thể bị `UP-TO-DATE` và không tạo lại file.
- Khi `--rerun-tasks`, output thay đổi dù declared inputs không đổi.
- Không thể tin cậy cache/reproducibility theo cùng input.

Khôi phục generator không chứa thời gian để sửa tận gốc.

### 10.5. Lỗi đường dẫn runtime

Thay `getResourceAsStream(...)` bằng đọc `Path.of("src/main/resources/config/app.properties")`. Chạy ở project directory có thể tình cờ thấy file nguồn, nhưng khi chạy từ nơi khác hoặc đóng gói JAR, path có thể không tồn tại và cũng **không đọc bản đã được expand**. Đó là lý do classpath resource tốt hơn cho data được đóng gói.

## 11. Reproducible JAR: hiểu đúng thứ tự file và timestamps

Một ứng dụng có thể tạo class files không đổi mà JAR checksum vẫn đổi vì ZIP metadata.

### 11.1. Archive controls

~~~groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

`AbstractArchiveTask` là Gradle archive task type; cần import nếu build script/logic không tự resolve type. Với Gradle 9.0+, các behavior reproducible timestamps/order đã là **default** theo tài liệu hiện hành; explicit config hữu ích khi tương thích phiên bản cũ hoặc làm rõ policy.

- `preserveFileTimestamps=false` tránh chèn mtime nguồn vào ZIP/JAR entries.
- `reproducibleFileOrder=true` dùng thứ tự entries nhất quán.
- Cả hai **không** tự sửa generated file chứa timestamp/UUID/hostname/absolute path.
- Các thông tin như manifest attributes, compiler/vendor/version, resource template inputs hoặc packaged dependency versions vẫn có thể thay đổi output.

### 11.2. Kiểm chứng hai clean builds

Linux/macOS:

~~~bash
./gradlew clean jar
sha256sum build/libs/stable-build-lab-1.0.0.jar

./gradlew clean jar
sha256sum build/libs/stable-build-lab-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean jar
Get-FileHash build/libs/stable-build-lab-1.0.0.jar -Algorithm SHA256

.\gradlew.bat clean jar
Get-FileHash build/libs/stable-build-lab-1.0.0.jar -Algorithm SHA256
~~~

Nếu cùng source/Gradle Wrapper/JDK/toolchain/settings và generator stable, **kỳ vọng** checksum giống nhau. Nếu khác, kiểm tra JAR entries/timestamps/manifest/generated data/bytecode differences. Không khẳng định mọi builds trên mọi OS/JDK vendor đều tự động byte-for-byte identical chỉ nhờ hai flags archive.

### 11.3. Thế nào là “mã sinh có tính tái lập”?

Một generator ổn định:
- Không ghi thời gian, random IDs, locale mặc định, absolute path.
- Có thứ tự duyệt inputs được sort.
- Chuẩn hóa newline/encoding.
- Có output root riêng, được Gradle theo dõi.
- Có input properties cho mọi thứ ảnh hưởng bytes output.
- Không mutate source tree.
- Kết quả khi chạy lại với cùng input là cùng bytes.

Khi những điều này đúng, build cache có cơ sở để mang lại lợi ích. Nhưng **cacheability** còn yêu cầu Gradle task được đánh dấu hỗ trợ và không dùng state external bị ẩn; không tự gắn `@CacheableTask` cho mọi generator trước khi kiểm chứng tính độc lập/tính xác định.

## 12. Generated resources: nối output task vào `processResources`

Ngoài Java source, bạn có thể muốn tạo text resource như `META-INF/build-info.txt` từ version cố định.

**Snippet minh họa** dùng custom task có input/output rõ, chạy trong project Java có build.gradle thích hợp:

~~~groovy
abstract class GenerateBuildInfo extends DefaultTask {
    @Input
    abstract Property<String> getVersionLabel()

    @OutputDirectory
    abstract DirectoryProperty getResourceDirectory()

    @TaskAction
    void writeInfo() {
        File f = new File(
            resourceDirectory.get().asFile,
            'META-INF/build-info.txt'
        )
        f.parentFile.mkdirs()
        f.setText("version=" + versionLabel.get() + "\n", 'UTF-8')
    }
}

def generateBuildInfo = tasks.register(
    'generateBuildInfo', GenerateBuildInfo
) {
    versionLabel.set('1.0.0')
    resourceDirectory.set(
        layout.buildDirectory.dir('generated/resources/build-info')
    )
}

tasks.named('processResources', Copy) {
    from(generateBuildInfo)
}
~~~

**Lưu ý:**
- Đây là một **mở rộng riêng**, không bắt buộc trong lab phần 9.
- `processResources.from(generateBuildInfo)` nhận outputs của task provider, giúp Gradle suy luận producer-consumer relationship.
- Source output root dành riêng cho `generateBuildInfo`, không đè lên `src/main/resources`.
- Nếu đã có một file `META-INF/build-info.txt` trong resources thông thường, `FAIL` sẽ phát hiện duplicate; sửa ownership.
- Nếu task đọc thêm commit SHA từ môi trường, phải khai SHA đó là input; với reproducible release nên dùng SHA đã xác định từ pipeline, không gọi Git command ngẫu nhiên trong task khi không theo dõi.

## 13. Source set, resources path và classpath

### 13.1. Quy ước Java plugin

| Nguồn | Directory mặc định | Output/consumer |
| --- | --- | --- |
| Java main | `src/main/java` | `compileJava` → `build/classes/java/main` |
| Java test | `src/test/java` | `compileTestJava` → `build/classes/java/test` |
| Main resources | `src/main/resources` | `processResources` → `build/resources/main` |
| Test resources | `src/test/resources` | `processTestResources` → `build/resources/test` |
| Generated Java (custom) | Task output riêng dưới `build/generated/sources/...` | Nối vào `sourceSets.main.java.srcDir(taskProvider)` |
| Generated resources | Task output riêng dưới `build/generated/resources/...` | Nối vào `processResources.from(taskProvider)` |

Các path output là conventions của Java plugin và có thể được custom; không hard-code chúng làm input trong một task mới nếu có Provider/property có thể nối.

### 13.2. Resource trong JAR được đọc ra sao?

Với file `src/main/resources/config/app.properties`, `jar` thông thường có entry `config/app.properties`. Trong Java:

~~~java
Main.class.getResourceAsStream("/config/app.properties")
~~~

Đường dẫn bắt đầu bằng `/` nên là **absolute resource name tương đối classpath root**, không phải OS absolute file path. Không viết `getResourceAsStream("src/main/resources/config/app.properties")` vì folder `src/main/resources` không phải một phần tên resource trong JAR.

### 13.3. Tại sao có lỗi duplicate class?

Nếu bạn vừa đặt generated `GeneratedGreeting.java` trong `src/main/java`, vừa thêm task output source directory chứa class cùng package/name, javac có thể báo `duplicate class: demo.generated.GeneratedGreeting`. Đây là xung đột **source/class declaration**, khác với duplicate resource trong `Copy`. Không có `DuplicatesStrategy.EXCLUDE` nào sửa chuẩn việc khai hai Java classes cùng qualified name trong compile source set.

Kiểm tra sourceSets, compile task sources, generated directories và annotation processor outputs để xác định **ai sở hữu generated type**.

## 14. Common failures: quy trình chẩn đoán nhanh

| Log/triệu chứng | Lớp lỗi | Bước xác minh |
| --- | --- | --- |
| `unmappable character for encoding US-ASCII` | Java source encoding | Xem bytes source, `JavaCompile.options.encoding` |
| Java console in `ChÃ o` | Runtime decode hoặc terminal | Kiểm tra `Properties.load(InputStream)` vs `Reader(UTF_8)` |
| Generated Java chứa ký tự sai | Generator output encoding | `setText(..., 'UTF-8')`, Java source encoding |
| `DuplicateFileCopyingException` | Copy/Jar resources | Tìm hai nguồn có cùng destination relative path |
| `Entry ... is a duplicate` | CopySpec duplicates policy | Chọn owner; `FAIL` khi cần fail-fast |
| Java code `FileNotFoundException` trên CI | CWD/absolute path/case sensitivity | `layout.*` hoặc classpath resources |
| `NoClassDefFoundError` | Runtime classpath/packaging | Dependencies, Jar manifest, classpath |
| `duplicate class` | Source generation | Search source sets, generated Java outputs |
| `processResources` qua nhưng resource missing | Sai resource path / pattern | Xem `build/resources/main`, JAR entries và `getResourceAsStream` |
| `compileJava` rerun liên tục | Input/output/generator nondeterminism | `--info` reasons, inspect generated bytes |
| `jar` checksum thay đổi sau clean | Reproducibility | Compare JAR entry metadata, manifest, generated content |
| `Task ... uses output of ... without dependency` | Implicit dependency thiếu | Wire provider/output property thay raw path |
| Cache miss bất ngờ | Input fingerprint thay đổi | Xem relative paths, normalized inputs, toolchain/env |
| Build ghi source tree | Configuration/task side effect | Chuyển outputs về `layout.buildDirectory` |
| Windows chạy, Linux lỗi case | File naming | Kiểm tra case chính xác trong Git |
| `java -version` khác Gradle compiler | Gradle toolchain | Kiểm tra Java toolchain và Gradle JVM riêng |

### 14.1. Lệnh kiểm tra theo lớp

~~~bash
./gradlew compileJava --info
./gradlew processResources --info
./gradlew jar --info
./gradlew run --quiet
./gradlew clean build --info
./gradlew help --configuration-cache
./gradlew help --configuration-cache
~~~

- `--info` cho biết task execution và lý do không `UP-TO-DATE` trong nhiều trường hợp.
- `--rerun-tasks` có thể dùng để **thử generator output determinism**, nhưng không phải fix production.
- `--configuration-cache` kiểm tra configuration-side behavior; build cache và configuration cache là hai cơ chế khác nhau.
- Các lệnh `run` chỉ tồn tại khi có Application plugin hoặc plugin tạo task `run` phù hợp.
- Trên CI, tránh đăng logs chứa private repository URLs/credentials/secret file paths.

### 14.2. Kiểm tra JAR có gì

Trên máy có JDK:

~~~bash
jar tf build/libs/stable-build-lab-1.0.0.jar
~~~

Trong output của lab, tìm:
- `demo/Main.class`.
- `demo/generated/GeneratedGreeting.class`.
- `config/app.properties`.

Không tìm `src/main/resources/...` bên trong JAR vì nó được copy tương đối từ resource root. Nếu file thiếu, điều tra `processResources`/`jar` inputs và task dependencies, không lập tức thêm absolute resource path vào Java code.

### 14.3. Khi có duplicate resource từ dependency JAR

Nếu runtime classpath chứa hai JARs đều có `META-INF/services/...`, Java classloader/ServiceLoader có thể truy cập nhiều service descriptors tùy classpath; đó **không tự là một `processResources` duplicate** trong project. Lỗi duplicate entry xuất hiện khi bạn **tự ghép/unpack** nhiều JARs vào một output archive hoặc copy tree.

Không sửa một vấn đề classpath bằng cách xóa arbitrary resource từ tất cả dependencies. Cần xác định có đang tạo fat jar hay không và merge policy ở artifact build task nào.

## 15. Khuyến nghị cho CI và multi-project

### 15.1. Mỗi task sinh file nên có output riêng

Với multi-project:

~~~text
:api:generateSources   -> api/build/generated/sources/api/
:client:generateSources-> client/build/generated/sources/client/
:server:generateConfig -> server/build/generated/resources/config/
~~~

Không viết outputs vào thư mục root dùng chung như `build/generated/java` của root hoặc `src/main/java` của project khác. Khi chạy `--parallel`, các tasks chồng lấn có thể tranh nhau xóa/ghi file.

### 15.2. Đừng giả định local và CI có cùng đường dẫn

Tất cả paths của source/resource được config tương đối qua Gradle Layout API hoặc file properties. CI workspace có thể là `/home/runner/work/...`, developer Windows là `D:\work\...`, nhưng build logic không nên lưu những absolute paths này vào generated files.

Nếu một external tool bắt buộc cần absolute path trong **process arguments**, có thể lấy từ Provider tại execution/configuration phù hợp nhưng **không đưa absolute path vào artifact bytes**, trừ khi đó là input nghiệp vụ cần thiết và được khai rõ.

### 15.3. Cố định môi trường tác động bytecode

- Pin Gradle Wrapper.
- Dùng Java toolchains/source release rõ.
- Kiểm soát generator/plugin versions, không dùng dynamic plugin versions tùy tiện.
- Chuẩn hóa UTF-8/LF trong repository và generator.
- Không dựa vào default locale/timezone cho generated data.
- Dùng reproducible archives options và so sánh hashes trên CI theo nhu cầu.
- Dùng dependency locking/verification khi reproducible dependency graph/supply chain quan trọng.

### 15.4. Dùng `.gitattributes` cho text files

Ví dụ khuyến nghị chung trong repository:

~~~gitattributes
*.java text eol=lf
*.groovy text eol=lf
*.properties text eol=lf
*.xml text eol=lf
~~~

Đây là **mẫu chính sách newline**, không ép encoding: cần lưu files UTF-8 bằng editor và kiểm tra khi migrate dữ liệu cũ. Với binary files, không ép `text`; Git đã có cơ chế nhận diện nhưng vẫn có thể thêm patterns `binary` phù hợp.

## 16. Bài tập có đáp án

### Bài 1 — UTF-8 source

File `Main.java` chứa chuỗi tiếng Việt UTF-8; Gradle `compileJava` báo `unmappable character`. Cần kiểm tra gì?

**Đáp án:** Bytes/source encoding có đúng UTF-8 không; `tasks.withType(JavaCompile).configureEach { options.encoding='UTF-8' }`; compiler/JDK và file BOM. Không dùng `options.release` để sửa encoding.

### Bài 2 — UTF-8 resource

`app.properties` được copy/filter UTF-8 nhưng Java in sai tiếng Việt. Khả năng lỗi ở đâu?

**Đáp án:** Java có thể dùng `Properties.load(InputStream)` Latin-1; dùng `InputStreamReader(..., UTF_8)` và `Properties.load(Reader)`. Nếu Java String đúng mà console vẫn sai, kiểm tra terminal encoding.

### Bài 3 — Relative path

Vì sao `new File('src/main/resources/config/app.properties')` trong custom task có thể lỗi ở multi-project?

**Đáp án:** Nó phụ thuộc process CWD, không bảo đảm là project directory. Dùng `layout.projectDirectory.file(...)` cho source, `layout.buildDirectory.dir(...)` cho output.

### Bài 4 — Classpath resources

Khi đóng gói JAR, app đọc `src/main/resources/config/app.properties` bằng Path API có nên không?

**Đáp án:** Không cho packaged resource. Tên runtime là `/config/app.properties` trên classpath; dùng `getResourceAsStream`.

### Bài 5 — Duplicate policy

Hai files từ thư mục khác nhau được copy vào `config/app.properties`. `EXCLUDE` giải quyết được lỗi root cause không?

**Đáp án:** Không chắc. Nó giữ mục đầu tiên và bỏ mục sau, có thể giấu lỗi ownership. Ưu tiên `FAIL` để phát hiện; sau đó sửa nguồn, đổi destination hoặc merge có chủ đích.

### Bài 6 — `WARN` và `INCLUDE`

`WARN` khác `INCLUDE` thế nào?

**Đáp án:** `WARN` ghi cảnh báo nhưng hành vi tạo duplicate giống `INCLUDE`; trong ZIP có thể có nhiều entries cùng tên, còn thư mục đích có thể bị ghi đè.

### Bài 7 — Generated source

Hai custom tasks cùng ghi `build/generated/sources`; một task xóa output cũ, task còn lại bị mất file. Lỗi là gì?

**Đáp án:** Outputs chồng lấn, task ownership không rõ. Tách output directories và wire dependencies qua task providers/outputs.

### Bài 8 — Input thiếu

Generator đọc `System.getenv('BUILD_ID')` nhưng không khai input. Có thể ra sao?

**Đáp án:** Thay env value có thể không làm task out-of-date, và cùng declared inputs có thể sinh output khác; khai input rõ qua Provider/Property và quyết định nó có thật sự cần trong generated content không.

### Bài 9 — Mã sinh thời gian

Generator thêm `Instant.now()` vào Java header. Hai lần `--rerun-tasks` khác hash. Cách sửa?

**Đáp án:** Bỏ timestamp/random; nếu cần provenance, dùng input cố định từ release pipeline, normalize output và khai dữ liệu ảnh hưởng bytes như `@Input`.

### Bài 10 — Jar reproducibility

`reproducibleFileOrder=true` và `preserveFileTimestamps=false` có đủ bảo đảm JAR hash luôn giống trên mọi máy không?

**Đáp án:** Không. Chúng chỉ ổn định archive entry ordering/timestamps; class files/toolchain, manifest, generated content, resources, dependency graph vẫn phải được kiểm soát.

### Bài 11 — Bài lab

Thực hiện phần 9 rồi:
1. Chạy `./gradlew clean run --quiet`, xác minh ba dòng stdout.
2. Dùng `jar tf` kiểm tra class và resource paths trong JAR.
3. Thêm duplicate resource như phần 10.3; xác nhận `processResources` FAIL.
4. Xóa duplicate, chạy hai lần `clean jar` và so SHA-256.
5. Thử đổi `stableVersion`/`version`, xem `processResources` được chạy lại và resource output thay đổi.
6. Gắn timestamp vào generator rồi chạy hai lần với `--rerun-tasks`; quan sát khác bytes; khôi phục.
7. Chạy test trên Windows/macOS/Linux nếu có, kiểm tra case-sensitive names và UTF-8.

**Tiêu chí đạt:** Bạn chỉ rõ được file nào bị đọc sai encoding; phân biệt CWD path và Gradle Layout/Java classpath; chọn duplicates strategy theo policy; và chứng minh generated Java/resource output là hàm xác định của declared inputs.

## 17. Checklist trước khi đưa build vào CI

- [ ] `JavaCompile.options.encoding` được đặt UTF-8 cho Java source.
- [ ] Resource filtering chỉ áp cho known text files, có `filteringCharset='UTF-8'`.
- [ ] Java runtime giải mã text rõ ràng, không nhầm `Properties.load(InputStream)` với UTF-8.
- [ ] Không hard-code absolute machine paths hoặc dựa vào `new File(relative)`.
- [ ] Resource path trong Java dùng classpath semantics nếu resource được đóng gói.
- [ ] Kiểm tra file/folder name case trên Linux CI.
- [ ] Dùng `layout.projectDirectory`/`layout.buildDirectory` và task file properties.
- [ ] `processResources`/`Copy`/`Jar` có duplicate policy rõ; không dùng `EXCLUDE` như thuốc chữa không kiểm tra.
- [ ] Các template inputs được khai, không filter binary assets.
- [ ] Mỗi generator có một output location riêng dưới build directory.
- [ ] Generated sources/resources nối bằng TaskProvider/output properties thay raw paths.
- [ ] Generator không ghi timestamp/random/host path vào output nếu chưa có policy/input cố định.
- [ ] Output files có encoding và newline ổn định.
- [ ] Test build `UP-TO-DATE` và `--rerun-tasks` để phát hiện non-determinism.
- [ ] Archives có reproducible timestamps/order policy; kiểm chứng SHA-256 khi cần.
- [ ] Không ghi vào source tree trong `processResources`/generator actions.
- [ ] Pin Gradle Wrapper, toolchain, generator plugin versions theo yêu cầu.
- [ ] Lỗi CI được điều tra đúng pha thay vì xóa cache hoặc vô hiệu hóa checks bừa bãi.

## 18. Tài liệu Gradle chính thức

- [Gradle — Working With Files](https://docs.gradle.org/current/userguide/working_with_files.html): paths, `CopySpec`, `from`/`into`, content filtering, charset, archive behaviors.
- [Gradle — Copy Task DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.Copy.html): `filteringCharset`, `filesMatching`, duplicates strategy.
- [Gradle — ProcessResources DSL](https://docs.gradle.org/current/dsl/org.gradle.language.jvm.tasks.ProcessResources.html): Java resource copy semantics.
- [Gradle — DuplicatesStrategy API](https://docs.gradle.org/current/javadoc/org/gradle/api/file/DuplicatesStrategy.html): `FAIL`/`EXCLUDE`/`INCLUDE`/`WARN`/`INHERIT`.
- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): generated sources, Java source sets và compile errors.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): `JavaCompile`, `processResources`, `jar`, Java toolchains.
- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): task inputs/outputs, inferred dependencies, up-to-date and stale outputs.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.register`, `tasks.named`, lazy providers.
- [Gradle — Reproducible Builds](https://docs.gradle.org/current/userguide/best_practices_security.html): reproducible archives và binary integrity.
- [Gradle — Jar DSL](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html): `preserveFileTimestamps` và `reproducibleFileOrder`.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): cacheable tasks và input normalization.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): tránh configuration-time side effects.
