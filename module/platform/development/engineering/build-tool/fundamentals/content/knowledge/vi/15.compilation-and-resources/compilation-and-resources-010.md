# Kiểm tra đầu ra biên dịch và phát hiện tệp cũ còn sót

Một dự án Java có thể biên dịch thành công nhưng artifact cuối cùng vẫn chứa class hoặc resource không còn thuộc mã nguồn hiện tại. Ví dụ, một class đã bị xóa khỏi `src/main/java` vẫn xuất hiện trong JAR; một tệp cấu hình cũ còn nằm trong thư mục resources; hoặc pipeline đóng gói nhầm output từ lần build trước. Những tệp này thường được gọi là **stale outputs** (đầu ra cũ còn sót).

Để phát hiện và xử lý đúng, cần hiểu Gradle ghi kết quả biên dịch ở đâu, task nào sở hữu từng thư mục output, Gradle quyết định chạy lại task như thế nào và cách kiểm tra nội dung artifact. Không nên chỉ nhìn dòng `BUILD SUCCESSFUL`: dòng này cho biết các task được yêu cầu đã hoàn tất theo trạng thái của chúng, nhưng không tự chứng minh mọi tệp trong gói đều đúng với source hiện tại.

## 1. Đầu ra biên dịch nằm ở đâu?

Khi dùng Java Plugin, Gradle đặt phần lớn output sinh ra trong thư mục `build/` của từng project. Một cấu trúc thường gặp:

```text
project/
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   └── test/
│       ├── java/
│       └── resources/
└── build/
    ├── classes/
    │   └── java/
    │       ├── main/
    │       └── test/
    ├── resources/
    │   ├── main/
    │   └── test/
    ├── generated/
    │   └── sources/
    │       └── annotationProcessor/
    │           └── java/
    │               ├── main/
    │               └── test/
    ├── libs/
    │   └── project-1.0.0.jar
    └── reports/
```

Các vị trí phổ biến:

| Output | Task thường tạo | Vị trí mặc định thường gặp |
|---|---|---|
| Class của source set `main` | `compileJava` | `build/classes/java/main` |
| Class của source set `test` | `compileTestJava` | `build/classes/java/test` |
| Resource chính đã xử lý | `processResources` | `build/resources/main` |
| Resource kiểm thử đã xử lý | `processTestResources` | `build/resources/test` |
| Generated source từ annotation processor | `compileJava` hoặc task compile tương ứng | Dưới `build/generated/sources/annotationProcessor/` |
| JAR chính | `jar` | `build/libs/` |
| Báo cáo kiểm thử | `test` | `build/reports/tests/test/` |

Đường dẫn có thể thay đổi theo Gradle version, plugin, source set và cấu hình của project. Không nên coi các đường dẫn này là cố định nếu build script đã tùy chỉnh output. Khi điều tra, hãy xem cấu hình task và output thực tế của project.

### Output trong multi-project build

Mỗi subproject thường có thư mục `build/` riêng:

```text
workspace/
├── settings.gradle
├── app/
│   └── build/
│       ├── classes/
│       └── libs/
└── core/
    └── build/
        ├── classes/
        └── libs/
```

Lệnh `./gradlew clean` thường yêu cầu task `clean` ở các project tham gia build. Khi chỉ muốn kiểm tra một module, có thể chạy task theo đường dẫn đầy đủ, ví dụ:

```bash
./gradlew :app:clean :app:build
```

Cần nhớ output của `:core` có thể được `:app` sử dụng thông qua project dependency. Khi điều tra artifact của ứng dụng, hãy xem cả output của module phụ thuộc nếu có dấu hiệu version hoặc class cũ được đưa vào.

## 2. Phân biệt source, generated source và build output

Ba loại tệp này có vòng đời khác nhau:

- **Source do developer quản lý:** nằm trong `src/main/java`, `src/test/java` hoặc source directory được khai báo. Đây là đầu vào của build và thường được quản lý trong version control.
- **Generated source:** được task hoặc annotation processor sinh ra trong quá trình build, thường nằm dưới `build/generated/`. Đây là output trung gian có thể được tạo lại.
- **Compiled output:** class file, resource đã xử lý, JAR hoặc báo cáo nằm trong `build/`. Đây cũng là output được tạo lại từ source và cấu hình.

Ví dụ:

```text
src/main/java/com/example/OldReport.java
    │
    └── compileJava
          └── build/classes/java/main/com/example/OldReport.class
```

Nếu developer xóa `OldReport.java`, class file cũ không còn được mong đợi trong output mới. Nếu class vẫn còn và được đưa vào JAR, ứng dụng có thể vô tình chứa code đã bị xóa khỏi source.

Không nên sửa trực tiếp file `.class` trong `build/classes` hoặc generated source để xử lý lỗi. Chúng sẽ bị tạo lại ở lần build sau và có thể che giấu nguyên nhân thực sự.

## 3. Stale output hình thành như thế nào?

Một tệp cũ có thể còn sót lại vì nhiều nguyên nhân:

1. Task sao chép file vào output directory nhưng không xóa những file không còn trong source.
2. Custom task tạo output nhưng khai báo thiếu input/output hoặc không dọn output cũ khi input bị xóa.
3. Hai task ghi vào cùng một thư mục, khiến output của task trước còn tồn tại sau khi task sau chạy.
4. Build script đổi output directory, nhưng thư mục cũ vẫn nằm lại và một task đóng gói khác vẫn đọc nó.
5. Pipeline tái sử dụng workspace hoặc artifact staging directory mà không làm sạch đúng phạm vi.
6. Fat JAR, shaded JAR hoặc container image được tạo từ một thư mục chứa output cũ.
7. Artifact từ lần build trước được tải hoặc triển khai nhầm.
8. Một task bị skip theo điều kiện trong khi pipeline vẫn sử dụng output cũ từ lần chạy trước.

Không phải mọi output cũ đều là lỗi. Một task có thể hợp lệ ở trạng thái `UP-TO-DATE` hoặc `FROM-CACHE` vì Gradle xác định output vẫn đúng với input hiện tại. Vấn đề xuất hiện khi output không còn phản ánh input hiện tại nhưng vẫn được dùng ở bước sau.

## 4. Gradle quản lý output và incremental compilation ra sao?

Gradle theo dõi input và output đã khai báo của task. Nếu input không thay đổi và output vẫn hợp lệ, task có thể được đánh dấu `UP-TO-DATE`. Nếu output được lấy từ build cache, task có thể hiển thị `FROM-CACHE`. Nếu input thay đổi, task thường cần chạy lại.

Với Java Plugin, `JavaCompile` hỗ trợ incremental compilation. Gradle và compiler có thể chỉ biên dịch phần source cần thiết thay vì biên dịch lại toàn bộ project. Việc theo dõi source đã xóa cũng là một phần của quản lý incremental compile output: output class tương ứng với source không còn tồn tại cần được loại khỏi kết quả được quản lý.

Tuy vậy, không nên suy rộng cơ chế đó sang mọi task. Các task copy file, task tự viết, generator và script tùy chỉnh có hành vi riêng. Một task copy không nhất thiết xóa các file đã có trong destination chỉ vì source file tương ứng không còn.

### Trạng thái task không đồng nghĩa với nội dung đã được kiểm chứng

| Trạng thái | Ý nghĩa | Cần làm gì khi điều tra stale output? |
|---|---|---|
| Task thực thi thành công | Action của task đã hoàn tất | Kiểm tra output có đúng nội dung mong đợi không |
| `UP-TO-DATE` | Gradle xác định input/output được theo dõi không cần chạy lại | Xác nhận input/output khai báo đầy đủ và không có đầu vào ẩn |
| `FROM-CACHE` | Output được khôi phục từ build cache | Kiểm tra task cacheable và input key có mô tả đầy đủ dữ liệu không |
| `NO-SOURCE` | Không có source phù hợp để task xử lý | Kiểm tra output cũ có được task khác sử dụng không |
| `SKIPPED` | Task bị bỏ qua theo điều kiện hoặc cấu hình | Kiểm tra bước sau có đang lấy output cũ không |
| `FAILED` | Task thất bại | Không coi output dở dang là artifact hợp lệ |

`BUILD SUCCESSFUL` có thể xuất hiện khi một số task là `UP-TO-DATE` hoặc `FROM-CACHE`; đây là hành vi bình thường. Cần tìm hiểu vì sao output được coi là hợp lệ, thay vì buộc mọi task chạy lại trong mọi build.

## 5. Xóa source rồi class file vẫn còn: cách điều tra

Giả sử trước đây project có:

```text
src/main/java/com/example/LegacyExporter.java
```

Sau một lần refactor, file source đã bị xóa. Nhưng trong JAR mới vẫn thấy:

```text
com/example/LegacyExporter.class
```

Hãy lần theo đường đi của class:

1. Kiểm tra source directory và source set có còn một bản `LegacyExporter.java` khác không.
2. Kiểm tra `compileJava` đang ghi vào output directory nào.
3. Kiểm tra có custom task nào sao chép class file hoặc tạo lại class đó không.
4. Kiểm tra `jar` đang lấy nội dung từ output của source set nào.
5. Kiểm tra có output directory cũ được đưa thêm vào `jar.from(...)` hay không.
6. Kiểm tra JAR cuối cùng thực sự được tạo trong lần build này, không phải file từ lần chạy trước.

Có thể kiểm tra output compile:

```bash
find build/classes/java/main -type f
```

Trên PowerShell:

```powershell
Get-ChildItem -LiteralPath 'build/classes/java/main' -Recurse -File |
    Select-Object -ExpandProperty FullName
```

Tìm tên class trong JAR:

```bash
jar tf build/libs/application.jar | grep 'LegacyExporter'
```

PowerShell có thể dùng:

```powershell
jar tf build/libs/application.jar | Select-String 'LegacyExporter'
```

Nếu class đã biến mất khỏi `build/classes/java/main` nhưng vẫn nằm trong JAR, vấn đề có thể nằm ở cấu hình đóng gói hoặc artifact JAR khác. Nếu class còn trong compile output, hãy xem task biên dịch, source set và các task ghi vào output directory đó.

### Khi nào nên chạy clean?

Nếu đã xác định output cũ còn sót và cần tái tạo toàn bộ output được quản lý trong build directory, chạy:

```bash
./gradlew clean build
```

Hoặc chỉ làm sạch module cụ thể:

```bash
./gradlew :app:clean :app:build
```

`clean` xóa thư mục build của project tương ứng rồi build tạo lại output. Nếu stale class biến mất sau clean, đó là bằng chứng output trước đó có vấn đề, nhưng chưa chỉ ra nguyên nhân gốc. Cần tiếp tục kiểm tra task nào đã để lại file, output có bị dùng chung hay task có khai báo đúng hay không.

Nếu clean xong mà class vẫn xuất hiện, nhiều khả năng nó được tạo lại từ source khác, generated source, dependency hoặc task đóng gói tùy chỉnh. Khi đó, chạy clean lặp lại không giải quyết được vấn đề.

## 6. Stale resource và sự khác nhau giữa `Copy` với `Sync`

Resource có thể bị sót theo cách khác class file. Ví dụ, source có:

```text
src/main/resources/
├── application.yml
└── templates/report.html
```

Sau đó `templates/report.html` bị xóa. Nếu task copy chỉ chép những file hiện đang có vào destination mà không đồng bộ destination, file đã xóa có thể vẫn nằm trong thư mục output.

Gradle có hai task type quan trọng:

- `Copy`: sao chép các file khớp source specification vào destination; không có mục đích tổng quát là làm destination giống hệt source bằng cách xóa mọi file thừa.
- `Sync`: đồng bộ destination với tập file được khai báo; các file thừa trong destination có thể bị xóa.

Ví dụ task copy:

```groovy
tasks.register('copyConfig', Copy) {
    from('src/main/config')
    into(layout.buildDirectory.dir('staging/config'))
}
```

Nếu source file bị xóa, không nên mặc định rằng `Copy` sẽ xóa bản cũ đã có trong `build/staging/config`.

Nếu mục tiêu là một staging directory chỉ chứa đúng tập file nguồn hiện tại, có thể dùng `Sync`:

```groovy
tasks.register('syncConfig', Sync) {
    from('src/main/config')
    into(layout.buildDirectory.dir('staging/config'))
}
```

`Sync` phù hợp với thư mục staging dành riêng cho task đó. Không dùng nó trên thư mục chứa file người dùng hoặc output của task khác, vì file không thuộc tập nguồn được khai báo có thể bị xóa.

Task `processResources` của Java Plugin dựa trên cơ chế copy. Khi cần xác nhận resource đã xóa có còn trong output hay không, hãy kiểm tra `build/resources/main` sau khi task chạy. Nếu custom pipeline cần destination được đồng bộ hoàn toàn, hãy cân nhắc `Sync` với output directory riêng và khai báo output rõ ràng.

## 7. Kiểm tra output của task `processResources`

Ví dụ source resource:

```text
src/main/resources/
├── application.yml
├── logback.xml
└── messages.properties
```

Output thường thấy:

```text
build/resources/main/
├── application.yml
├── logback.xml
└── messages.properties
```

Nếu resource cũ vẫn còn, kiểm tra:

- Có file trùng tên ở một resource directory khác của source set không?
- Source set có khai báo thêm `resources.srcDir(...)` không?
- Có task copy tùy chỉnh ghi vào `build/resources/main` không?
- Có filtering hoặc rename rule làm file được tạo dưới tên khác không?
- Có task đóng gói đọc cả thư mục cũ ngoài output của `processResources` không?

Xem cấu hình source set:

```groovy
sourceSets {
    main {
        resources {
            srcDirs = ['src/main/resources', 'src/shared/resources']
        }
    }
}
```

Khi có nhiều resource roots, một file có thể được lấy từ một thư mục mà người điều tra chưa để ý. Không nên kết luận file là stale chỉ vì nó không nằm trong thư mục đầu tiên.

## 8. Kiểm tra JAR và nội dung artifact cuối cùng

Output compile đúng chưa đủ; cần xác nhận archive được tạo từ đúng output.

Liệt kê nội dung JAR:

```bash
jar tf build/libs/application-1.0.0.jar
```

Lọc class/resource cụ thể:

```bash
jar tf build/libs/application-1.0.0.jar | grep -E 'LegacyExporter|application.yml|report.html'
```

Trên PowerShell:

```powershell
jar tf build/libs/application-1.0.0.jar |
    Select-String 'LegacyExporter|application.yml|report.html'
```

Xem thông tin class trong JAR:

```bash
javap -classpath build/libs/application-1.0.0.jar -public com.example.LegacyExporter
```

Nếu class nằm trong nested JAR của executable archive, `javap` cần classpath trỏ tới JAR chứa class hoặc cần giải nén nested artifact ra vị trí tạm để kiểm tra.

### Kiểm tra manifest và version

JAR có thể chứa manifest:

```bash
unzip -p build/libs/application-1.0.0.jar META-INF/MANIFEST.MF
```

Hoặc dùng công cụ `jar` để trích xuất manifest. Kiểm tra `Implementation-Version`, `Main-Class` và các metadata nếu build có cấu hình. Manifest chỉ là metadata; không chứng minh toàn bộ nội dung archive đúng. Cần kiểm tra cả danh sách entry và class/resource quan trọng.

### So sánh artifact giữa các lần build

Nếu cần xác định pipeline có dùng nhầm artifact cũ, hãy ghi lại:

- Đường dẫn artifact.
- Kích thước và thời gian tạo.
- Version/commit metadata được gắn vào artifact.
- Checksum của file.
- Build invocation tạo artifact đó.

Ví dụ tạo SHA-256:

```bash
sha256sum build/libs/application-1.0.0.jar
```

PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'build/libs/application-1.0.0.jar'
```

Checksum giúp xác nhận hai file có cùng nội dung byte hay không. Nó không tự xác nhận file đúng; cần đối chiếu với artifact đã được build và xác minh từ nguồn tin cậy.

## 9. Output cũ trong generated source và annotation processing

Annotation processor và code generator cũng có thể để lại output. Ví dụ một processor sinh:

```text
build/generated/sources/annotationProcessor/java/main/
└── com/example/CustomerMapperImpl.java
```

Nếu annotation hoặc source đầu vào bị xóa, output generated tương ứng cần được quản lý đúng bởi task/compiler. Processor không hỗ trợ incremental processing, hoặc custom generator không theo dõi input/output chính xác, có thể khiến build chạy lại rộng hơn hoặc để lại file không mong muốn.

Khi nghi ngờ generated source cũ:

1. Kiểm tra generated source directory thực tế của task.
2. Xác định task/processor nào sở hữu directory đó.
3. Kiểm tra annotation processor path và source set.
4. Kiểm tra incremental processing metadata nếu processor hỗ trợ Gradle incremental annotation processing.
5. Chạy clean để tái tạo output trong trường hợp cần xác định file có phải tàn dư của lần build cũ không.
6. Nếu file được sinh lại sau clean, tìm source hoặc processor rule vẫn tạo nó.

Không chỉnh sửa generated source bằng tay và không đặt generated source vào `src/main/java`. Một generator tùy chỉnh nên ghi vào output directory riêng, khai báo input/output và có hành vi xử lý source bị xóa rõ ràng.

## 10. Khai báo output đúng cho custom task

Gradle chỉ có thể quản lý output một cách đáng tin cậy khi task mô tả nơi ghi kết quả. Ví dụ một task tạo file report:

```groovy
abstract class GenerateReport extends DefaultTask {
    @InputFiles
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract ConfigurableFileCollection getInputFiles()

    @OutputFile
    abstract RegularFileProperty getReportFile()

    @TaskAction
    void generate() {
        File output = reportFile.get().asFile
        output.parentFile.mkdirs()
        output.text = inputFiles.files
            .sort { it.path }
            .collect { it.name }
            .join(System.lineSeparator())
    }
}

tasks.register('generateReport', GenerateReport) {
    inputFiles.from(fileTree('src/main/java') {
        include '**/*.java'
    })
    reportFile.set(layout.buildDirectory.file('reports/source-list.txt'))
}
```

Trong ví dụ:

- `@InputFiles` mô tả tập tệp ảnh hưởng kết quả.
- `@OutputFile` mô tả file task tạo ra.
- `@TaskAction` thực hiện công việc.
- Output nằm trong `build/`, nơi có thể được tái tạo.

Nếu task đọc thêm một file cấu hình hoặc một project property nhưng không khai báo, Gradle có thể không nhận ra output cần cập nhật. Nếu task tạo nhiều file trong một thư mục, nên dùng `@OutputDirectory` và bảo đảm task quản lý chính xác tập output của nó.

### Không cho nhiều task ghi chung một output directory

Ví dụ thiết kế dễ gây vấn đề:

```groovy
tasks.register('generateApi') {
    outputs.dir(layout.buildDirectory.dir('generated/shared'))
    doLast {
        // Ghi API source vào generated/shared
    }
}

tasks.register('generateModel') {
    outputs.dir(layout.buildDirectory.dir('generated/shared'))
    doLast {
        // Ghi model source vào cùng generated/shared
    }
}
```

Hai task cùng sở hữu một output directory. Điều này khiến Gradle khó xác định task nào tạo file nào, có thể gây xung đột khi chạy song song, làm cache không đáng tin và khiến file cũ khó được dọn đúng cách.

Nên tách output:

```groovy
tasks.register('generateApi') {
    outputs.dir(layout.buildDirectory.dir('generated/api'))
}

tasks.register('generateModel') {
    outputs.dir(layout.buildDirectory.dir('generated/model'))
}
```

Nếu một task tổng hợp cần cả hai, hãy khai báo input của nó từ output của hai task tương ứng. Mỗi task nên sở hữu output riêng và không xóa dữ liệu của task khác.

## 11. `clean`, `--rerun-tasks` và `--refresh-dependencies` khác nhau

Ba lệnh/tùy chọn này thường bị dùng lẫn nhau, nhưng tác động khác nhau:

| Lệnh/tùy chọn | Tác động chính | Có xóa build output cũ không? |
|---|---|---|
| `clean` | Xóa thư mục build được task clean quản lý | Có, với build directory của project được clean |
| `--rerun-tasks` | Yêu cầu thực thi lại task thay vì bỏ qua theo up-to-date/cache trong invocation đó | Không tự xóa output directory trước khi task chạy |
| `--refresh-dependencies` | Kiểm tra lại trạng thái dependency đã resolve | Không, không phải công cụ dọn compile output |

Ví dụ:

```bash
./gradlew clean build
./gradlew build --rerun-tasks
./gradlew build --refresh-dependencies
```

`--rerun-tasks` có thể hữu ích khi muốn kiểm tra task action có thực sự tạo lại output không. Tuy nhiên, nếu task copy không xóa file cũ, chạy lại task vẫn có thể để lại file đó. `clean` xóa build directory trước, nên phù hợp để xác định output cũ có phải tàn dư của lần chạy trước hay không.

`--refresh-dependencies` dành cho dependency resolution. Nó không làm sạch `build/classes` hoặc `build/resources`.

### Không chạy clean một cách máy móc

Build tăng dần và build cache giúp tiết kiệm thời gian. Chạy `clean` trước mọi build có thể loại bỏ lợi ích đó. Hãy dùng clean khi cần tái tạo output từ đầu, xác nhận stale output, hoặc khi quy trình phát hành yêu cầu workspace sạch theo chính sách đã định.

Đồng thời, không đặt dữ liệu cần giữ lâu dài vào `build/`. `clean` được thiết kế để xóa build output; file người dùng hoặc dữ liệu bền vững phải nằm ở vị trí khác.

## 12. Kiểm tra task graph và output directory

Để biết task nào tạo output, hãy quan sát task graph và cấu hình task.

Liệt kê task:

```bash
./gradlew tasks --all
```

Xem các task sẽ chạy mà không thực thi:

```bash
./gradlew jar --dry-run
```

Bật log chi tiết:

```bash
./gradlew compileJava --info
./gradlew processResources --info
./gradlew jar --info
```

`--dry-run` giúp thấy task graph nhưng không xác nhận nội dung output. `--info` có thể cung cấp thông tin vì sao task chạy hoặc bị bỏ qua. Khi cần thêm chi tiết về lỗi, dùng `--stacktrace`.

Với Kotlin DSL, có thể xem output directory từ task type trong build logic hoặc log cấu hình. Không nên dựa vào tên thư mục mặc định nếu project đã đặt `destinationDirectory` khác.

Ví dụ cấu hình output compile tùy chỉnh:

```kotlin
tasks.named<JavaCompile>("compileJava") {
    destinationDirectory.set(layout.buildDirectory.dir("classes/custom-main"))
}
```

Khi đổi output path, kiểm tra các task downstream như `classes`, `jar`, test và custom packaging có dùng output provider đúng hay không. Không để task đóng gói vẫn đọc cả thư mục output cũ.

## 13. Kiểm tra source set và resource roots

Nếu một class hoặc resource tưởng đã xóa nhưng vẫn xuất hiện, có thể file còn nằm trong source directory khác.

Ví dụ:

```groovy
sourceSets {
    main {
        java.srcDirs = ['src/main/java', 'src/generated/java']
        resources.srcDirs = ['src/main/resources', 'src/shared/resources']
    }
}
```

Project này có nhiều source roots. Xóa file trong `src/main/java` không loại bỏ bản sao cùng tên trong `src/generated/java`.

Hãy tìm tất cả source roots được khai báo, bao gồm source set do plugin tạo. Kiểm tra task compile đang dùng source collection nào. Với generated sources, tìm task generator và dependency giữa generator với compile.

Trên Linux/macOS có thể tìm file theo tên:

```bash
find src -name 'LegacyExporter.java'
find build -name 'LegacyExporter.class'
```

Trên PowerShell:

```powershell
Get-ChildItem -LiteralPath 'src' -Recurse -File -Filter 'LegacyExporter.java'
Get-ChildItem -LiteralPath 'build' -Recurse -File -Filter 'LegacyExporter.class'
```

Nếu có nhiều kết quả, kiểm tra đường dẫn và source set của từng file trước khi xóa. Không xóa file chỉ dựa trên tên mà chưa xác định ai sở hữu nó.

## 14. Stale output trong CI và pipeline đóng gói

CI runner có thể dùng workspace mới cho mỗi job, nhưng nhiều hệ thống tối ưu bằng cách tái sử dụng workspace, cache thư mục hoặc tải artifact từ job trước. Khi đó, output cũ có thể lọt vào bước đóng gói.

Một số tình huống:

- Job build không gọi `clean`, nhưng staging directory nằm ngoài Gradle build directory.
- Pipeline restore cache toàn bộ `build/` thay vì chỉ cache dependency hoặc output được kiểm soát.
- Task copy artifact vào `dist/` nhưng không xóa file version cũ.
- Job publish lấy `*.jar` từ thư mục chứa nhiều version thay vì file vừa build.
- Docker build context chứa JAR cũ và Dockerfile sao chép nhầm file.
- Pipeline deploy dùng tag container mutable hoặc artifact từ run khác.

### Giữ staging directory có nội dung xác định

Nếu thư mục phân phối cần chứa đúng một tập artifact, hãy tạo staging directory riêng và đồng bộ nó:

```groovy
tasks.register('stageDistribution', Sync) {
    from(tasks.named('jar'))
    into(layout.buildDirectory.dir('distribution'))
}
```

Trong build thực tế, cần cấu hình `from` theo output provider hoặc file collection cụ thể của task `jar`; ví dụ trên minh họa ý tưởng dùng `Sync` để destination không giữ file thừa. Không dùng `Sync` trên một thư mục dùng chung với dữ liệu ngoài phạm vi task.

Khi publish, tham chiếu artifact đầu ra cụ thể của task thay vì wildcard rộng như `build/libs/*.jar` nếu thư mục có thể chứa nhiều phiên bản hoặc classifier. Điều đó giúp pipeline chọn đúng file vừa được tạo.

### Không cache mọi thứ một cách tùy tiện

Cache nên chứa dữ liệu có thể tái sử dụng và có khóa hợp lệ. Tránh cache staging directory có file cũ, secret hoặc output không được task khai báo. Nếu task có input ẩn, build cache có thể trả lại output không phù hợp vì Gradle không biết một giá trị quan trọng đã thay đổi.

## 15. Quy trình chẩn đoán stale file theo từng lớp

Khi phát hiện class/resource cũ, đừng xóa cả workspace ngay lập tức. Hãy xác định file xuất hiện lần đầu ở tầng nào:

1. **Source roots:** file có còn ở một source/resource directory nào khác không?
2. **Generated output:** processor hoặc generator có tạo lại file không?
3. **Compile/resource output:** file đã có trong `build/classes` hoặc `build/resources` chưa?
4. **Packaging input:** task JAR/distribution có lấy thêm thư mục cũ không?
5. **Artifact:** file có thực sự nằm trong JAR/WAR/ZIP/image vừa tạo không?
6. **Deployment:** môi trường đang chạy đúng artifact của build hiện tại hay artifact từ lần trước?

Bảng gợi ý:

| Quan sát | Nơi cần kiểm tra tiếp |
|---|---|
| File còn trong `src/` | Source roots, generated source được commit hoặc bản sao trong module khác |
| File không còn trong source nhưng còn trong generated directory | Processor/generator và output ownership |
| File còn trong `build/classes` | `JavaCompile`, output path, incremental compilation và task ghi class tùy chỉnh |
| File còn trong `build/resources` | `processResources`, nhiều resource roots, `Copy`/`Sync` và task copy riêng |
| File không còn trong output folder nhưng còn trong JAR | `jar.from`, custom packaging, archive cũ hoặc artifact khác |
| JAR đúng nhưng runtime vẫn dùng class cũ | Classloader, server-provided libraries, container image hoặc deploy target |
| Chỉ CI có file cũ | Workspace reuse, restored cache, staging directory và artifact selection |

Sau khi khoanh vùng, chạy clean/build có mục tiêu để xác nhận. Nếu clean giải quyết tạm thời nhưng lỗi tái xuất hiện, cần sửa task hoặc pipeline tạo ra stale output.

## 16. Ví dụ hoàn chỉnh: file resource đã xóa vẫn nằm trong gói

Giả sử project có custom task:

```groovy
tasks.register('copyTemplates', Copy) {
    from('src/main/templates')
    into(layout.buildDirectory.dir('staging/templates'))
}
```

Lần build đầu có hai file:

```text
src/main/templates/
├── invoice.html
└── legacy-invoice.html
```

Task copy cả hai vào staging. Sau đó developer xóa `legacy-invoice.html` khỏi source. Lần chạy tiếp theo, `Copy` chép `invoice.html`, nhưng destination có thể vẫn còn `legacy-invoice.html` từ lần trước.

Nếu task đóng gói đọc toàn bộ `build/staging/templates`, artifact vẫn chứa template cũ.

Sửa bằng cách dùng `Sync` nếu destination phải phản ánh chính xác source hiện tại:

```groovy
tasks.register('syncTemplates', Sync) {
    from('src/main/templates')
    into(layout.buildDirectory.dir('staging/templates'))
}
```

Sau khi đổi task, có thể chạy:

```bash
./gradlew clean syncTemplates
```

Kiểm tra `build/staging/templates` và nội dung archive sau đó. Cần đảm bảo staging directory chỉ do `syncTemplates` sở hữu để `Sync` không xóa output không liên quan.

## 17. Ví dụ hoàn chỉnh: class cũ xuất hiện trong JAR

Giả sử project từng có class `com.example.LegacyJob`. Sau refactor, class đã được đổi tên thành `ScheduledJob`, nhưng JAR vẫn chứa cả hai class.

Quy trình:

**Bước 1: tìm source còn lại**

```bash
find src -name '*LegacyJob*'
```

**Bước 2: tìm compiled output**

```bash
find build/classes -name '*LegacyJob*'
```

**Bước 3: kiểm tra archive**

```bash
jar tf build/libs/app.jar | grep 'LegacyJob'
```

**Bước 4: làm sạch và build lại**

```bash
./gradlew clean :app:jar
```

**Bước 5: kiểm tra lại**

```bash
find build/classes -name '*LegacyJob*'
jar tf build/libs/app.jar | grep 'LegacyJob'
```

Nếu class biến mất sau clean, hãy kiểm tra tại sao output trước đó còn lại: task compile có output directory tùy chỉnh không, có task khác ghi vào đó không, task JAR có include thêm thư mục cũ không, hay pipeline dùng archive không được tạo từ lần build mới?

Nếu class vẫn xuất hiện sau clean, tìm nguồn khác tạo nó: source root bổ sung, generated source, dependency được unpack vào JAR hoặc task packaging riêng.

## 18. Nguyên tắc tổ chức output dễ bảo trì

- Đặt generated output dưới `build/` hoặc một thư mục build chuyên dụng có thể tái tạo.
- Mỗi task sở hữu output directory riêng; tránh nhiều task ghi chung một nơi.
- Khai báo đầy đủ task inputs và outputs.
- Nối output task trước với input task sau qua provider/file collection phù hợp.
- Dùng `Sync` khi cần destination phản ánh chính xác tập source; dùng `Copy` khi chỉ cần chép file và không yêu cầu xóa file thừa.
- Không để task đóng gói quét wildcard quá rộng nếu output directory có thể chứa file cũ.
- Không chỉnh sửa class/generated source trực tiếp.
- Không lưu dữ liệu người dùng cần giữ lâu dài trong build directory.
- Kiểm tra archive cuối cùng và artifact được deploy, không chỉ compile output.
- Chỉ dùng clean khi cần tái tạo output từ đầu hoặc xác nhận giả thuyết stale output.

## 19. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| `BUILD SUCCESSFUL` nghĩa là không có file cũ | Build thành công chỉ xác nhận các task được yêu cầu hoàn tất; nội dung artifact vẫn cần được kiểm tra. |
| `UP-TO-DATE` nghĩa là Gradle bỏ quên thay đổi | Nó có nghĩa input/output được theo dõi được coi là hợp lệ; nếu có đầu vào ẩn, cần sửa khai báo task. |
| `--rerun-tasks` tương đương `clean` | Rerun thực thi task lại nhưng không tự xóa mọi file cũ trong output directory. |
| `--refresh-dependencies` xóa class cũ | Tùy chọn này làm mới kiểm tra dependency, không dọn compile output. |
| Mọi task copy tự xóa file không còn trong source | `Copy` không đồng bộ destination; dùng `Sync` nếu cần xóa file thừa. |
| Xóa file trong `src` là class file tự biến mất ở mọi trường hợp | JavaCompile quản lý incremental output, nhưng task tùy chỉnh, output dùng chung hoặc packaging riêng vẫn có thể để lại file. |
| Xóa toàn bộ `build/` là cách sửa tận gốc | Clean có thể xác nhận output cũ, nhưng phải tìm task hoặc pipeline tạo ra nó. |
| JAR đúng nghĩa là ứng dụng runtime đang dùng đúng JAR đó | Classloader, server, container và deploy process có thể nạp artifact khác. |

## 20. Nguyên tắc cần ghi nhớ

Đầu ra biên dịch và đóng gói là sản phẩm được tạo từ source, cấu hình và dependency. Gradle theo dõi input/output của task để hỗ trợ incremental build và build cache, nhưng hành vi dọn file cũ phụ thuộc loại task và cách output được khai báo. JavaCompile quản lý class output của nó; task copy thông thường không tự làm destination giống hệt source, trong khi Sync được thiết kế để đồng bộ và loại file thừa.

Khi nghi ngờ stale output, hãy tìm file từ source roots tới generated directory, compile/resource output, archive và môi trường runtime. Dùng `dependencies`/task graph để hiểu task, `jar tf` để kiểm tra archive, `javap` để xem class và checksum để đối chiếu artifact. `clean` hữu ích để tái tạo output từ đầu, nhưng nếu file xuất hiện lại thì cần sửa task, output ownership hoặc pipeline. Kiểm tra đúng từng lớp giúp build ổn định và bảo đảm artifact được phát hành thực sự phản ánh mã nguồn hiện tại.
