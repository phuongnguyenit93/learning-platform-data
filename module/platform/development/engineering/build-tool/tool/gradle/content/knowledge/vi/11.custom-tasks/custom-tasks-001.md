# Khi nào dùng task có sẵn và khi nào tạo task type riêng trong Gradle

## 1. Câu hỏi cốt lõi: tái sử dụng hay tự xây dựng?

Gradle dùng **task** để mô tả một đơn vị công việc trong quá trình build: biên dịch, kiểm thử, sao chép file, đóng gói, tạo mã nguồn, kiểm tra chất lượng hoặc phát hành artifact. Khi cần bổ sung một công việc, người mới thường viết ngay:

~~~kotlin
tasks.register("viecMoi") {
    doLast {
        // Công việc tùy chỉnh
    }
}
~~~

Cách này hợp lệ với những thao tác rất nhỏ, nhưng **không phải luôn là lựa chọn tốt nhất**. Gradle đã có nhiều **task type** và plugin chuyên xử lý công việc phổ biến. Khi dùng lại chúng, ta nhận được API đầu vào/đầu ra, quy tắc thực thi, khả năng tích hợp và các cơ chế tối ưu đã được thiết kế sẵn. Chỉ nên tạo **custom task type** khi nghiệp vụ thực sự không khớp task có sẵn, hoặc cần một thành phần build có hợp đồng rõ ràng và tái sử dụng lâu dài.

Bài học giúp bạn lựa chọn giữa bốn phương án:

1. **Cấu hình task đã được plugin tạo**: ví dụ `test`, `compileJava`, `jar`.
2. **Đăng ký thêm một instance của task type có sẵn**: `Copy`, `Sync`, `Zip`, `Delete`, `JavaExec`, v.v.
3. **Đăng ký task đơn giản với `doLast` hoặc `doFirst`**: thích hợp khi công việc nhỏ, cục bộ và không có mô hình đầu vào/đầu ra phức tạp.
4. **Viết custom task type** kế thừa `DefaultTask`, khai báo properties và `@TaskAction`: phù hợp với logic đặc thù, cần kiểm tra hợp đồng, tính lazy, khả năng tái sử dụng và tối ưu build.

**Quy tắc lựa chọn ngắn:** ưu tiên plugin/task đã có; nếu chỉ thiếu một trường hợp chạy mới, đăng ký thêm **instance** của loại đó; khi công việc thật sự khác bản chất và cần mô hình riêng, mới viết **task type**.

## 2. Task, task type và task instance khác nhau như thế nào?

Ba khái niệm cần tách bạch:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Task** | `test`, `jar`, `copyDocs` | Công việc có tên trong đồ thị build |
| **Task type** | `Test`, `Jar`, `Copy`, `DefaultTask`, `UppercaseTextTask` | Kiểu đối tượng định nghĩa API và hành vi của task |
| **Task instance** | Task tên `copyDocs` thuộc type `Copy` | Một task cụ thể được đăng ký/cấu hình từ một type |
| **Task action** | `doLast { ... }` hoặc method có `@TaskAction` | Phần công việc Gradle chạy khi thực thi task |
| **TaskProvider<T>** | Giá trị trả về từ `tasks.register<Copy>(...)` | Handle dùng để cấu hình/lấy task theo cách lazy |

Một type có thể được dùng cho nhiều instance:

~~~kotlin
tasks.register<Copy>("copyGuides") {
    from("docs/guides")
    into(layout.buildDirectory.dir("guides"))
}

tasks.register<Copy>("copySamples") {
    from("docs/samples")
    into(layout.buildDirectory.dir("samples"))
}
~~~

Cả hai task trên thuộc **cùng type `Copy`**, nhưng có tên, nguồn và đích khác nhau. Không cần viết hai lớp custom task để làm hai phép sao chép. Khi chạy `copyGuides`, Gradle không tự chạy `copySamples`, trừ khi dependency graph có quan hệ yêu cầu điều đó.

Mỗi task có thể thuộc một plugin: chẳng hạn plugin `java` thường tạo các task liên quan biên dịch/kiểm thử/đóng JAR. **Cấu hình task đã tồn tại** khác với **đăng ký task mới**, và cả hai khác với **định nghĩa một class task type mới**.

## 3. Bảng quyết định: chọn cách nào cho công việc nào?

| Nhu cầu | Cách ưu tiên | Vì sao? |
| --- | --- | --- |
| Chạy unit test theo JUnit Platform | Cấu hình task `Test` do Java plugin tạo | `Test` đã biết cách chạy test, báo cáo, classpath, test filters |
| Đổi encoding của biên dịch Java | Cấu hình `JavaCompile` | Tránh viết lại trình biên dịch |
| Sao chép resource từ thư mục A sang B | `Copy` | Đã có `from`, `into`, filters, copy specs |
| Đồng bộ thư mục đích theo nguồn, loại file thừa | `Sync` | Có semantics đồng bộ, không cần tự xóa file |
| Tạo archive ZIP | `Zip` | Có API archive, filename, destination |
| Xóa output tạm có phạm vi xác định | `Delete` | Có API delete; cần cẩn trọng đường dẫn |
| Chạy một Java main class | `JavaExec` hoặc plugin `application` | Có API classpath/JVM args/main class |
| Chỉ in thông báo hướng dẫn dùng local | Task thường có `doLast` | Ít mã, không cần tạo class |
| Tạo file từ một định dạng dữ liệu đặc thù | Custom task type nếu không có plugin phù hợp | Cần input/output và action chuyên biệt |
| Kiểm tra schema riêng của tổ chức trên hàng trăm module | Task type + plugin dùng chung | Có hợp đồng có kiểu và tái sử dụng |
| Upload, deploy, gọi API có side effect | Ưu tiên plugin chuyên dụng hoặc custom task không cache tùy tiện | Cần retry, authentication, permissions, side effects |
| Tạo nhiều task cùng logic nhưng nguồn/đích khác nhau | Một task type + nhiều instance | Tránh nhân bản logic |

### Quy trình quyết định 5 câu

1. **Gradle hoặc plugin chính thức đã có task làm công việc này chưa?** Nếu có, cấu hình nó.
2. **Task type có sẵn phù hợp hoàn toàn nhưng cần chạy thêm lần khác không?** Tạo thêm một instance qua `tasks.register<Type>`.
3. **Công việc chỉ nhỏ, một lần, không cần hợp đồng input/output hay tái sử dụng?** `doLast` có thể đủ.
4. **Có logic riêng, file input/output, nhiều tham số, hoặc nhiều module dùng chung?** Tạo một class task type với properties và `@TaskAction`.
5. **Có plugin bên thứ ba đã giải quyết bài toán tốt hơn không?** Xem mức độ tin cậy, bảo trì, tương thích phiên bản, quyền truy cập của plugin và độ cần thiết; không tự viết lại một hệ thống phức tạp chỉ vì chưa tìm hiểu plugin.

Mục tiêu không phải giảm số dòng bằng mọi giá, mà là **mô hình build rõ, dự đoán được và dễ bảo trì**.

## 4. Dùng task có sẵn khi chỉ cần cấu hình hành vi

Một dự án Java thường không cần tự viết task để biên dịch, kiểm thử và tạo JAR. Plugin Gradle đã cung cấp chúng.

Ví dụ **`build.gradle.kts`**:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test

plugins {
    java
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

- `plugins { java }` áp dụng Java plugin, tạo mô hình source sets và các task cần thiết.
- `tasks.withType<JavaCompile>().configureEach` cấu hình các task biên dịch Java, không thay phần logic biên dịch của Gradle.
- `tasks.withType<Test>().configureEach` chỉ cấu hình cách chạy test. Nó **không tự thêm** dependency JUnit 5: để test thực sự chạy, dự án còn phải khai báo test dependencies phù hợp.
- `configureEach` giúp cấu hình theo kiểu lazy, áp dụng cho task thuộc type cần thiết mà không bắt buộc tạo toàn bộ instance sớm.

Nếu chỉ muốn cấu hình task tên `test`:

~~~kotlin
tasks.named<Test>("test") {
    useJUnitPlatform()
}
~~~

Điểm khác biệt: `named<Test>("test")` chỉ nhắm đúng task tên `test`; `withType<Test>().configureEach` nhắm tất cả task thuộc type `Test`.

**Khi nào không tạo task type riêng?** Khi yêu cầu chỉ là đổi `options.encoding`, thêm compiler arguments, đổi test filtering hoặc cấu hình JAR manifest. Những việc này đã nằm trong API của task có sẵn.

## 5. Đăng ký instance mới của type có sẵn: Copy, Zip, Sync

Giả sử bạn có thư mục `docs` và muốn đưa tài liệu vào thư mục build, rồi tạo một archive. Không cần custom task type.

**File `build.gradle.kts` độc lập:**

~~~kotlin
import org.gradle.api.tasks.Copy
import org.gradle.api.tasks.bundling.Zip

tasks.register<Copy>("copyDocs") {
    group = "documentation"
    description = "Copy the docs directory into build/docs-copy"
    from("docs")
    into(layout.buildDirectory.dir("docs-copy"))
}

tasks.register<Zip>("zipDocs") {
    group = "documentation"
    description = "Package docs as a ZIP file"
    from("docs")
    archiveFileName.set("docs.zip")
    destinationDirectory.set(layout.buildDirectory.dir("archives"))
}
~~~

Tạo trước file `docs/hello.txt` bằng editor, với nội dung `Hello Gradle`, rồi chạy:

~~~bash
# Linux/macOS
./gradlew copyDocs
./gradlew zipDocs
~~~

~~~powershell
# Windows PowerShell
.\gradlew.bat copyDocs
.\gradlew.bat zipDocs
~~~

Khi đầu vào có file và build directory giữ mặc định, kết quả thường là:

~~~text
build/docs-copy/hello.txt
build/archives/docs.zip
~~~

Đây là **đường dẫn output**, không phải stdout cố định từ Gradle. Tùy cấu hình project/Gradle, console còn có các dòng `> Task :...`, thông báo up-to-date hoặc các warning.

Phân tích:

- `Copy` đã biết cách sao chép; `from` và `into` là **mã cấu hình** task chứ không thực hiện copy ngay khi build script được đọc.
- `Zip` đã biết cách đóng gói; `archiveFileName` và `destinationDirectory` là các properties cấu hình output.
- `layout.buildDirectory.dir(...)` là provider trỏ tới đường dẫn bên trong build directory theo cách Gradle quản lý, tốt hơn hardcode toàn bộ đường dẫn tuyệt đối.
- Task `copyDocs` và `zipDocs` độc lập. Một task không tự chạy sau task kia nếu không có quan hệ `dependsOn` hoặc quan hệ mô hình phù hợp.

### 5.1. Sync không giống Copy

`Sync` giống thao tác copy có thêm semantics **đồng bộ đích với tập nội dung nguồn**; file không còn nằm trong nguồn có thể bị loại khỏi đích. Dùng khi thư mục đích là vùng staging **do task sở hữu riêng**:

~~~kotlin
import org.gradle.api.tasks.Sync

tasks.register<Sync>("stageDocs") {
    from("docs")
    into(layout.buildDirectory.dir("staged-docs"))
}
~~~

**Cảnh báo:** không trỏ `Sync` vào thư mục chứa dữ liệu người dùng hay thư mục dùng chung. Nó có thể xóa những file thừa trong vùng đích để kết quả khớp nguồn. Nếu chỉ cần copy thêm file mà không quản lý cả vùng đích, `Copy` thích hợp hơn.

### 5.2. Delete cần giới hạn phạm vi

~~~kotlin
import org.gradle.api.tasks.Delete

tasks.register<Delete>("removeGeneratedScratch") {
    delete(layout.buildDirectory.dir("scratch"))
}
~~~

Đây là một ví dụ dùng type có sẵn cho thao tác xóa. Chỉ xóa thư mục output được quản lý bởi build; tránh đường dẫn dựa trên đầu vào chưa xác thực hoặc biến môi trường không tin cậy. Trong dự án thực tế, ưu tiên task `clean` do plugin cung cấp khi muốn dọn output build thông thường.

## 6. Một task thường với doLast phù hợp khi nào?

Không phải công việc nhỏ nào cũng cần một class. Với thao tác thuần túy để học Gradle, in thông báo hoặc một tác vụ điều phối ngắn, `tasks.register` kết hợp `doLast` là đủ.

**File `build.gradle.kts` chạy được:**

~~~kotlin
tasks.register("helloBuild") {
    group = "help"
    description = "Print a short build greeting"

    doLast {
        println("Hello from Gradle")
    }
}
~~~

Chạy:

~~~bash
./gradlew -q helloBuild
~~~

Trên PowerShell:

~~~powershell
.\gradlew.bat -q helloBuild
~~~

Dòng stdout do task in:

~~~text
Hello from Gradle
~~~

Một khối `doLast { ... }` là **action được đăng ký** cho task; code trong đó không chạy chỉ vì Gradle cấu hình build. `group`, `description` thuộc **mã cấu hình task**; chúng giúp task dễ tìm trong `./gradlew tasks`.

Sử dụng task thường hợp lý khi:

- Công việc rất nhỏ, chỉ dành cho project hiện tại.
- Không cần validate nhiều input/parameters.
- Không cần mô hình output, incremental build hay Build Cache.
- Không có nhu cầu dùng lại logic ở nhiều module.

**Không nên kéo dài kiểu này** để đọc nhiều file, xử lý dữ liệu phức tạp, gọi mạng hoặc ghi nhiều output mà không khai báo input/output. Một task `doLast` không có outputs thường được Gradle coi là cần chạy khi được yêu cầu; việc có một đoạn logic trong `doLast` không tự tạo cơ chế up-to-date hoặc cache.

### 6.1. Anti-pattern: làm việc trong pha cấu hình

Đoạn sau **không nên áp dụng** trong build thực:

~~~kotlin
tasks.register("generateReport") {
    // KHONG NEN: thuc thi IO ngay khi task duoc realize.
    val data = file("data/input.txt").readText()

    doLast {
        println(data.length)
    }
}
~~~

Việc đọc file nằm ngay trong **mã cấu hình task**, không phải action, khiến Gradle có thể đọc sớm ngay cả khi chỉ đang lập kế hoạch hoặc công cụ nào đó realize task. Dữ liệu cũng bị capture trong closure; điều này làm reasoning về Configuration Cache khó hơn.

Muốn xử lý file đúng cách: để **I/O vào execution**, công khai input/output với Gradle, không truy cập `Project`/script object trong action nếu không phù hợp với Configuration Cache; cách bền vững là một custom task type có kiểu.

## 7. Khi nào cần custom task type?

Tạo custom task type khi công việc có **bản chất riêng**, không được task type có sẵn hỗ trợ đầy đủ và cần một hoặc nhiều đặc tính:

1. **Hợp đồng có kiểu:** input file, output file, chế độ xử lý, options, flags hoặc nhiều thuộc tính có validation rõ.
2. **Incremental/up-to-date:** Gradle cần biết input nào ảnh hưởng output nào để bỏ qua việc không đổi.
3. **Build Cache:** cần điều kiện cache rõ ràng khi task thực sự deterministic và có thể tái sử dụng kết quả.
4. **Tái sử dụng:** nhiều module đăng ký cùng loại task với các input/output khác nhau.
5. **Kiểm thử build logic:** tách một class, task action và cấu hình để dễ bảo trì, test độc lập hoặc đưa vào plugin.
6. **Configuration Cache:** tránh action capture đối tượng không serialize được, dùng managed properties/provider theo cơ chế Gradle.
7. **Phân định trách nhiệm:** task type định nghĩa **cách làm**, build script chỉ định **làm với dữ liệu nào**.

Ví dụ hợp lý: một công cụ của tổ chức cần đọc một file văn bản rồi chuyển đổi nội dung theo quy tắc nội bộ thành một file output, và được dùng ở nhiều subproject. Nếu không có plugin phù hợp, một `UppercaseTextTask` custom giúp xác định rõ input/output và action.

Ví dụ **không đáng** tạo class riêng: chỉ thêm một bản sao file bằng `Copy`, đổi định dạng ZIP bằng `Zip`, hoặc cấu hình task `Test` mà Java plugin đã tạo.

## 8. Ví dụ hoàn chỉnh: custom task type có InputFile, OutputFile và TaskAction

Ví dụ này nhận file UTF-8, biến toàn bộ chữ cái thành chữ hoa và ghi ra file UTF-8 khác. Logic đủ nhỏ để hiểu nhưng thể hiện cấu trúc của custom task type thật.

### 8.1. Khai báo type trong build.gradle.kts

**File `build.gradle.kts` (độc lập):**

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

@CacheableTask
abstract class UppercaseTextTask : DefaultTask() {

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sourceFile: RegularFileProperty

    @get:OutputFile
    abstract val destinationFile: RegularFileProperty

    @TaskAction
    fun convert() {
        val original = sourceFile.get().asFile.readText(Charsets.UTF_8)
        val output = destinationFile.get().asFile

        output.parentFile.mkdirs()
        output.writeText(original.uppercase(), Charsets.UTF_8)
    }
}

tasks.register<UppercaseTextTask>("uppercaseMessage") {
    group = "generation"
    description = "Convert a UTF-8 text file to uppercase"

    sourceFile.set(layout.projectDirectory.file("data/message.txt"))
    destinationFile.set(
        layout.buildDirectory.file("generated/message-uppercase.txt")
    )
}
~~~

**Phần trong class `UppercaseTextTask`:**

- `DefaultTask` là base class cho task tùy chỉnh.
- `@get:InputFile` khai báo `sourceFile` là file đầu vào mà Gradle cần theo dõi.
- `@get:PathSensitive(PathSensitivity.RELATIVE)` mô tả cách Gradle xét phần đường dẫn của file input; relative path giúp tránh khóa cache hoàn toàn vào absolute path của workspace khi semantics cho phép.
- `@get:OutputFile` khai báo file kết quả.
- `RegularFileProperty` là managed property cho file; Gradle hỗ trợ tính lazy và xác thực property.
- `@TaskAction` đánh dấu method Gradle gọi khi task thực sự thực thi.
- `@CacheableTask` khai báo task type có thể dùng Build Cache. **Chỉ nên đánh dấu như vậy khi output là hàm deterministic của những inputs được khai báo**. Trong ví dụ, input là nội dung file, output là chuỗi uppercase bằng API Kotlin; không phụ thuộc network hoặc đồng hồ.

**Phần đăng ký instance:**

- `tasks.register<UppercaseTextTask>("uppercaseMessage")` tạo một task provider theo kiểu mới.
- `sourceFile.set(...)` và `destinationFile.set(...)` cấu hình dữ liệu cần đọc/ghi; không chuyển đổi file ở thời điểm cấu hình.
- `layout.projectDirectory.file(...)` trỏ tới input thuộc project; `layout.buildDirectory.file(...)` là provider cho output bên trong thư mục build.

### 8.2. Chuẩn bị input và chạy thử

Tạo thủ công file UTF-8 **`data/message.txt`** (UTF-8 không BOM) trong project, nội dung chính xác:

~~~text
hello gradle
~~~

Sau đó chạy:

~~~bash
# Linux/macOS
./gradlew uppercaseMessage --console=plain
~~~

~~~powershell
# Windows PowerShell
.\gradlew.bat uppercaseMessage --console=plain
~~~

Đọc file output `build/generated/message-uppercase.txt`. Nội dung chính xác:

~~~text
HELLO GRADLE
~~~

Dòng này là **nội dung file**, không phải stdout được task in; task không dùng `println`. Trên console, Gradle hiển thị tên task/trạng thái tùy lần build và phiên bản, chẳng hạn chạy thực tế, `UP-TO-DATE` hoặc `FROM-CACHE`.

Lần chạy sau, nếu input/output không đổi và Gradle có đủ trạng thái cần thiết, task có thể được đánh dấu `UP-TO-DATE`. Để thử cơ chế Build Cache, có thể chạy:

~~~bash
./gradlew uppercaseMessage --build-cache
~~~

Cờ `--build-cache` bật dùng Build Cache cho lời gọi; **không bảo đảm** lần nào cũng có cache hit. Task có thể cần chạy để tạo cache entry lần đầu, hoặc build bị thay đổi đầu vào/implementation.

### 8.3. Thử nhiều instance cùng một type

Nếu có hai file input khác nhau, bạn chỉ cần đăng ký thêm task, **không copy toàn bộ method convert**:

~~~kotlin
tasks.register<UppercaseTextTask>("uppercaseNotes") {
    sourceFile.set(layout.projectDirectory.file("data/notes.txt"))
    destinationFile.set(
        layout.buildDirectory.file("generated/notes-uppercase.txt")
    )
}
~~~

Đây là **snippet bổ sung** cho file ở mục 8.1 (vì sử dụng type `UppercaseTextTask` đã được khai báo). Mỗi instance có input/output của riêng nó, nhưng cùng một implementation. Khi thêm instance, phải bảo đảm output không bị hai task khác nhau cùng ghi vào một đường dẫn; overlapping outputs làm kết quả và cache khó dự đoán.

## 9. Vì sao phải khai báo input/output?

Gradle không thể biết công việc của custom code nếu bạn chỉ đọc và ghi file bằng Java/Kotlin API mà không khai báo. Các annotation giúp Gradle biết:

- Input nào khiến kết quả có thể thay đổi.
- Output nào thuộc task.
- Task có thể bỏ qua vì `UP-TO-DATE` hay cần chạy lại.
- Có thể lưu/khôi phục kết quả trong Build Cache hay không.
- Task có được validate đầy đủ trước khi chạy hay không.

Một số annotation cần nhận diện:

| Annotation / kiểu | Mục đích | Ví dụ |
| --- | --- | --- |
| `@Input` | Giá trị dữ liệu, flag hoặc option | `Property<String>`, `Property<Boolean>` |
| `@InputFile` | Một file đầu vào | `RegularFileProperty` |
| `@InputFiles` | Nhiều file đầu vào | `ConfigurableFileCollection` |
| `@InputDirectory` | Thư mục đầu vào | `DirectoryProperty` |
| `@Classpath` | Một classpath; áp dụng normalization phù hợp | Dependency classpath của task |
| `@PathSensitive` | Xác định cách đường dẫn đóng góp vào fingerprint | `PathSensitivity.RELATIVE` |
| `@OutputFile` | File đầu ra | `RegularFileProperty` |
| `@OutputDirectory` | Thư mục đầu ra | `DirectoryProperty` |
| `@Nested` | Object phức tạp chứa properties tiếp tục được Gradle phân tích | Nhóm tùy chọn có kiểu |
| `@Internal` | Không tham gia mô hình input/output | Thuộc tính chỉ phục vụ nội bộ, không quyết định kết quả |
| `@Optional` | Input hợp lệ khi không có | Chỉ dùng với property có thể vắng mặt theo hợp đồng |
| `@TaskAction` | Phương thức thực hiện công việc của task | `fun convert()` |

Đừng đánh dấu property thật sự ảnh hưởng output là `@Internal` chỉ để tránh lỗi validation; điều đó có thể dẫn tới kết quả cũ được tái sử dụng sai.

**Input mang nội dung nhạy cảm:** không đưa secret vào output, task logs hoặc cache một cách tùy tiện; với dữ liệu nhạy cảm, xem chính sách cache và isolation của CI. Không coi `@Input` là một kho bảo mật secret.

### 9.1. @CacheableTask không phải “bật nhanh” cho mọi thứ

Chỉ đánh dấu task type có thể cache khi:

1. Output có thể tái tạo hoàn toàn từ các input được khai báo, phiên bản implementation và môi trường ảnh hưởng được mô hình hóa.
2. Không dựa vào thời gian thực, số ngẫu nhiên không kiểm soát, trạng thái mạng hoặc dữ liệu bên ngoài không khai báo.
3. Không tạo tác dụng phụ ngoài output đã khai báo.
4. Việc tái sử dụng output ở máy khác là hợp lệ và an toàn.

Task publish artifact, gửi email, deploy, đổi trạng thái server hoặc thực hiện giao dịch bên ngoài thường **không phù hợp** với cách cache output như một phép chuyển đổi file. Nên dùng plugin chuyên dụng hoặc custom task có semantics rõ về idempotency, credentials, retry và failure; không gắn `@CacheableTask` chỉ để tăng tốc.

## 10. Task type đặt ở đâu: build.gradle.kts, buildSrc hay plugin riêng?

Việc đặt class trong build script như mục 8 giúp học nhanh, nhưng khi build logic lớn nên tách code:

| Nơi đặt logic | Phù hợp khi | Lưu ý |
| --- | --- | --- |
| `build.gradle.kts` | Demo, một task nhỏ và chỉ một project | Khó tái sử dụng rộng; script phình to nếu có nhiều class |
| `buildSrc/src/main/kotlin/` | Logic dùng trong cùng một multi-project build | `buildSrc` là build riêng; thay đổi có thể tác động cấu hình các project |
| Included build/convention plugins như `build-logic` | Nhiều module cần quy tắc chung | Có thể kiểm thử, versioning và tách ranh giới rõ |
| Gradle plugin riêng | Logic cần chia sẻ giữa repository hoặc tổ chức | Cần duy trì API, test, phân phối và khả năng tương thích |

**Ví dụ cấu trúc khi tách build logic:**

~~~text
my-project/
├── settings.gradle.kts
├── build.gradle.kts
├── data/
│   └── message.txt
└── buildSrc/
    ├── build.gradle.kts
    └── src/main/kotlin/
        └── UppercaseTextTask.kt
~~~

Ở đây, class đặt trong `UppercaseTextTask.kt` và build script chỉ đăng ký task/configure properties. Đây là **sơ đồ minh họa**, không phải file buildSrc hoàn chỉnh: khi tách code thật, buildSrc cần plugin/dependencies Gradle thích hợp, khai báo class, package và import tương ứng. Với nhiều repository, convention plugin hoặc plugin chuyên dụng thường dễ kiểm soát hơn các đoạn script copy/paste.

Lựa chọn điểm đặt phụ thuộc phạm vi dùng lại. **Tạo type riêng** không đồng nghĩa bắt buộc **xuất bản một plugin riêng** ngay từ đầu.

## 11. So sánh Kotlin DSL và Groovy DSL cho task type

Nếu chỉ dùng task có sẵn, hai DSL khác nhau chủ yếu ở cú pháp.

**Kotlin DSL:**

~~~kotlin
import org.gradle.api.tasks.Copy

tasks.register<Copy>("copyDocs") {
    from("docs")
    into(layout.buildDirectory.dir("docs-copy"))
}
~~~

**Groovy DSL:**

~~~groovy
tasks.register('copyDocs', Copy) {
    from 'docs'
    into layout.buildDirectory.dir('docs-copy')
}
~~~

Với custom task type, Kotlin thường dùng abstract properties và getter annotations:

~~~kotlin
@get:InputFile
abstract val sourceFile: RegularFileProperty

@TaskAction
fun convert() {
    // Thuc thi cong viec
}
~~~

Trong Groovy, type tương đương có thể khai báo abstract getters/properties và các annotation Gradle; cú pháp sẽ khác nhưng **hợp đồng Gradle về input/output/action không thay đổi**. Không dùng cú pháp method call Groovy trong file `.gradle.kts`; Kotlin DSL kiểm tra type và overload của API.

Cần tra đúng tài liệu của task type, thay vì giả định vì cả hai có cặp `{ ... }` nên cú pháp bên trong giống nhau hoàn toàn.

## 12. Lazy configuration: register, named và configureEach

Custom task type nên được kết hợp với **Task Configuration Avoidance** để không tạo/cấu hình mọi task quá sớm.

~~~kotlin
val docsCopy = tasks.register<Copy>("docsCopy") {
    from("docs")
    into(layout.buildDirectory.dir("docs-copy"))
}

tasks.register("prepareDocs") {
    dependsOn(docsCopy)
}
~~~

Đây là snippet dùng type `Copy` và `Task` trong build script, mô tả việc dùng **`TaskProvider`** trong quan hệ dependency. `dependsOn(docsCopy)` cho Gradle biết khi chạy `prepareDocs` thì `docsCopy` phải được thực thi trước nếu cần. Một task chưa được chọn vẫn không tự chạy action.

Những API thường gặp:

- `tasks.register<Type>("name") { ... }`: đăng ký task mới theo cách lazy.
- `tasks.named<Type>("name") { ... }`: cấu hình task đã được đăng ký theo type và tên.
- `tasks.withType<Type>().configureEach { ... }`: cấu hình các task thuộc type theo cách lazy.
- `tasks.getByName("name")` và một số API `create(...)`: có thể realize task sớm; tránh dùng chỉ để truy cập property có thể cấu hình qua provider.

**Sự khác biệt quan trọng:** mã trong khối `register`/`named` dùng để **cấu hình** khi task được realize; `doLast` hoặc `@TaskAction` làm công việc khi task **thực thi**, và có thể không chạy nếu task đã `UP-TO-DATE`, được khôi phục `FROM-CACHE`, bị skip hoặc không thuộc task graph.

## 13. Configuration Cache và custom task type

**Configuration Cache** lưu một phần mô hình cấu hình build để tái sử dụng ở những lần chạy sau. Với custom task type:

- Khai báo input/output dưới dạng managed properties và provider.
- Tránh đọc file, mở network, ghi output hoặc tính toán nặng trong lúc cấu hình.
- Không truy cập `project`, `Task.project` hay script instance tùy tiện bên trong `@TaskAction`; một số truy cập như vậy bị cấm khi chạy với Configuration Cache.
- Dùng `layout.projectDirectory` và `layout.buildDirectory` trong lúc cấu hình để gán provider; action sử dụng giá trị property đã cấu hình thay vì hỏi lại `Project`.
- Tránh capture các object/services không hỗ trợ serialization trong action.
- Kiểm tra plugin/task khi bật `--configuration-cache` và xử lý báo cáo vi phạm; không giả định custom task sẽ tương thích chỉ nhờ có `@TaskAction`.

Ví dụ ở mục 8 cố ý chuyển input/output file qua `RegularFileProperty` và để `convert()` chỉ dùng properties của task. Đây là mô hình phù hợp hơn việc để action gọi `project.file(...)` hoặc đọc property của `Project`.

**Configuration Cache khác Build Cache:** cái thứ nhất giảm chi phí **cấu hình build**; cái thứ hai tái sử dụng **output task**. Một task type có thể tuân thủ Configuration Cache nhưng không cacheable, hoặc cacheable mà build logic xung quanh vẫn có vấn đề với Configuration Cache.

## 14. Những lỗi phổ biến khi quyết định và triển khai

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Tự viết hàm copy file dài dòng bằng `doLast` | Không tận dụng task type `Copy` | Thay bằng `tasks.register<Copy>` với `from`/`into` |
| Task custom chạy lại mọi lần dù input không đổi | Không khai báo input/output, hoặc có output không ổn định | Dùng properties và annotations đúng hợp đồng |
| Task custom báo lỗi input file chưa được cấp | `@InputFile` không có giá trị/file hợp lệ | Cấu hình `sourceFile.set(...)`; bảo đảm file tồn tại hoặc đổi hợp đồng cho đúng |
| Task không tái sử dụng được output từ Build Cache | Chưa đánh dấu cacheable, cache chưa bật hoặc cache miss | Chỉ dùng `@CacheableTask` khi deterministic; kiểm tra `--build-cache` |
| Cùng output bị hai task ghi | Output paths chồng chéo | Tách riêng output của từng task hoặc thiết kế ownership rõ |
| Dùng `Sync` khiến file trong đích bị xóa | Không hiểu Sync quản lý toàn bộ destination | Dùng thư mục staging riêng hoặc chuyển sang `Copy` |
| Dùng `Delete` và xóa nhầm dữ liệu | Đường dẫn quá rộng hoặc không được kiểm tra | Chỉ xóa output biết rõ, không dùng path do input không tin cậy |
| `Unresolved reference: from` | Đăng ký task thường chứ không phải `Copy` | Chỉ rõ type `register<Copy>` |
| `@TaskAction` dùng `project.file` rồi Configuration Cache báo lỗi | Action truy cập Project lúc execution | Truyền `RegularFileProperty` từ cấu hình, chỉ dùng property trong action |
| Nhiều subproject copy/paste task logic | Chưa tách thành type/plugin dùng chung | Đưa type vào build logic chung, đăng ký các instances khác nhau |
| Dùng `@Internal` để né task validation | Gradle không biết input thật | Khai báo `@Input...`/`@Output...` đúng, không che dữ liệu ảnh hưởng output |
| Task deploy bị gắn `@CacheableTask` | Side effects ngoài Gradle output không cache-safe | Bỏ cacheability, dùng plugin hoặc task type phù hợp |
| Build script bị chậm do đọc file khi cấu hình | I/O đặt sai thời điểm | Chuyển vào `@TaskAction`, khai báo input, dùng providers |

### 14.1. Cách chẩn đoán từng bước

Nếu thấy task chạy chậm hoặc bất ngờ chạy lại:

~~~bash
# Quan sát lý do task được chạy hoặc bị bỏ qua
./gradlew uppercaseMessage --info --console=plain

# Kiểm tra cơ chế Build Cache khi task type đáp ứng điều kiện
./gradlew uppercaseMessage --build-cache --info --console=plain

# Kiểm tra Configuration Cache
./gradlew uppercaseMessage --configuration-cache --console=plain

# Chạy lại task, bỏ qua up-to-date checks theo cơ chế Gradle
./gradlew uppercaseMessage --rerun-tasks --console=plain
~~~

Dùng những lệnh trên khi project có task `uppercaseMessage` từ mục 8. Những cờ này có vai trò khác nhau:

- `--info` bổ sung thông tin chẩn đoán; không nên chia sẻ log chưa kiểm tra secret.
- `--build-cache` yêu cầu sử dụng Build Cache cho những task cacheable, không chắc chắn sẽ tạo `FROM-CACHE`.
- `--configuration-cache` thử lưu/tái sử dụng cấu hình nếu build logic đáp ứng yêu cầu.
- `--rerun-tasks` bỏ qua up-to-date thông thường để yêu cầu thực thi lại task; vẫn không biến một task bị disable hoặc thiếu input thành task chạy thành công.

Quan sát thêm vị trí output thật và task graph, không chỉ dựa vào một dòng log.

## 15. Bài tập tình huống: lựa chọn giải pháp đúng

**Bài 1.** Bạn cần gộp thư mục hướng dẫn từ hai module vào một thư mục staging. Nên viết custom `MergeDocsTask` không?  
**Gợi ý:** trước tiên thử `Copy` hoặc `Sync`, khai báo nhiều `from` và `into`. Nếu chỉ cần tập hợp file, type có sẵn có thể đáp ứng. Xem xung đột tên file và ownership destination.

**Bài 2.** Nhóm muốn đổi `testLogging` hoặc dùng JUnit Platform cho tất cả test tasks. Nên tạo một subclass của `Test`?  
**Đáp án:** thường không; cấu hình `tasks.withType<Test>().configureEach { ... }`. `Test` đã có cơ chế chạy test và báo cáo.

**Bài 3.** Bạn cần parse một định dạng nội bộ, kiểm tra schema, phát sinh file Java source theo quy tắc doanh nghiệp và dùng cho nhiều module. Lựa chọn nào?  
**Đáp án:** nếu chưa có plugin phù hợp, custom task type có `@InputFile`/`@OutputDirectory` hoặc các properties thích hợp, `@TaskAction`, khai báo quan hệ với biên dịch; đưa vào convention/plugin để tái sử dụng.

**Bài 4.** Tác vụ chỉ in `Welcome developers` khi chạy một lệnh thủ công. Có cần tạo type không?  
**Đáp án:** không; task thường với `doLast` là đủ.

**Bài 5.** Hai task đều tạo `build/result.txt` và bạn muốn cache output cả hai. Ổn không?  
**Đáp án:** không nên; overlapping outputs khiến ownership và việc theo dõi/caching không tin cậy. Mỗi task nên có output riêng hoặc thiết kế lại pipeline.

**Bài 6.** Cần tự đồng bộ thư mục nhưng không được xóa file do người dùng thêm vào destination. Chọn `Sync` hay `Copy`?  
**Đáp án:** thường chọn `Copy`, vì `Sync` có semantics xóa file không thuộc nguồn trong vùng đích.

**Bài 7.** Custom task đã có `@TaskAction` nhưng vẫn không `UP-TO-DATE`. Vì sao?  
**Đáp án:** `@TaskAction` chỉ đánh dấu phương thức thực thi, không tự định nghĩa inputs/outputs; cần khai báo chính xác các properties và kiểm tra task outcome.

**Bài 8.** Task chạy network API để publish release. Có nên đánh dấu `@CacheableTask` để lần hai không gửi request?  
**Đáp án:** không dùng Build Cache thay cho semantics của thao tác publish. Ưu tiên plugin chuyên dụng và kiểm soát idempotency/credentials/failure; external side effects không được mô hình hóa thành output cache thông thường.

**Bài 9.** Bạn đang dùng `tasks.register<Copy>("copyDocs")` ở nhiều project, chỉ khác nguồn và đích. Có cần clone class Copy?  
**Đáp án:** không; đăng ký các instances từ `Copy` hoặc đặt quy tắc đăng ký chung trong convention plugin khi số module lớn.

**Bài 10.** Người viết task gọi `project.file(...)` trong `@TaskAction` và bật Configuration Cache thì báo lỗi. Cách sửa?  
**Đáp án:** chuyển việc xác định file sang cấu hình task, truyền bằng `RegularFileProperty`/`DirectoryProperty` và để action chỉ dùng property đã cấp; tránh truy cập Project lúc execution.

## 16. Checklist khi thiết kế một công việc Gradle mới

Trước khi viết custom task type, hãy tự trả lời:

- [ ] Có task type/plugin đã xử lý được nghiệp vụ này chưa?
- [ ] Chỉ cần cấu hình task được plugin tạo hay cần đăng ký một task instance mới?
- [ ] Nếu viết `doLast`, công việc có thực sự nhỏ và không cần hợp đồng input/output phức tạp?
- [ ] Nếu tạo custom task type, input/output đã được khai báo đúng và có thể validate chưa?
- [ ] Task action có tránh thực hiện I/O tại pha configuration không?
- [ ] Output có do task sở hữu riêng và không chồng chéo với task khác không?
- [ ] Task có deterministic, không có side effects và thực sự phù hợp với `@CacheableTask` không?
- [ ] Có dùng `TaskProvider`, `register`/`named`/`configureEach` để giữ cấu hình lazy không?
- [ ] Có cân nhắc Configuration Cache, secret handling và các plugin liên quan không?
- [ ] Logic sẽ chỉ sống trong project hay cần tách thành build logic/plugin dùng chung?
- [ ] Đã kiểm tra task outcome và output thật thay vì suy từ tên task chưa?

## 17. Tài liệu tham khảo chính thức

- [Gradle — Working with Tasks](https://docs.gradle.org/current/userguide/more_about_tasks.html): các task types, task actions và cấu hình.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): phát triển task class, properties và `@TaskAction`.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): khai báo inputs/outputs và up-to-date checks.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): cacheability và tái sử dụng output.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `register`, `named`, `configureEach`, `TaskProvider`.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): các điều kiện để tái sử dụng trạng thái cấu hình.
- [Gradle — Authoring Maintainable Builds](https://docs.gradle.org/current/userguide/organizing_gradle_projects.html): tổ chức build logic và module.
- [Gradle Kotlin DSL API](https://docs.gradle.org/current/kotlin-dsl/): chữ ký chính xác của `Copy`, `Sync`, `Zip`, `DefaultTask` và task APIs.

**Kết luận:** không viết custom task type chỉ vì muốn thêm một task có tên mới. **Tái sử dụng task/plugin có sẵn trước**, cấu hình hoặc đăng ký instance theo nhu cầu; `doLast` dành cho việc nhỏ; custom task type dành cho logic đặc thù cần hợp đồng input/output, kiểm thử, cacheability và tái sử dụng rõ ràng.